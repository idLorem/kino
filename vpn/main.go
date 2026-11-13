package main

import (
	"bufio"
	"context"
	"encoding/base64"
	"encoding/hex"
	"errors"
	"fmt"
	"io"
	"net"
	"net/netip"
	"os"
	"strconv"
	"strings"
	"time"

	"golang.zx2c4.com/wireguard/conn"
	"golang.zx2c4.com/wireguard/device"
	"golang.zx2c4.com/wireguard/tun/netstack"
)

type wgConf struct {
	addrs    []netip.Addr
	dns      []netip.Addr
	mtu      int
	uapi     strings.Builder
	hasPeer  bool
	endpoint string
}

func b64hex(s string) (string, error) {
	b, err := base64.StdEncoding.DecodeString(strings.TrimSpace(s))
	if err != nil || len(b) != 32 {
		return "", errors.New("bad key")
	}
	return hex.EncodeToString(b), nil
}

func parse(r io.Reader) (*wgConf, error) {
	c := &wgConf{mtu: 1280}
	sc := bufio.NewScanner(r)
	section := ""
	for sc.Scan() {
		line := strings.TrimSpace(sc.Text())
		if i := strings.IndexByte(line, '#'); i >= 0 {
			line = strings.TrimSpace(line[:i])
		}
		if line == "" {
			continue
		}
		if strings.HasPrefix(line, "[") {
			section = strings.ToLower(strings.Trim(line, "[] "))
			if section == "peer" {
				c.hasPeer = true
			}
			continue
		}
		k, v, ok := strings.Cut(line, "=")
		if !ok {
			continue
		}
		k, v = strings.ToLower(strings.TrimSpace(k)), strings.TrimSpace(v)
		switch section + "." + k {
		case "interface.privatekey":
			h, err := b64hex(v)
			if err != nil {
				return nil, fmt.Errorf("PrivateKey: %w", err)
			}
			fmt.Fprintf(&c.uapi, "private_key=%s\n", h)
		case "interface.address":
			for _, p := range strings.Split(v, ",") {
				pf, err := netip.ParsePrefix(strings.TrimSpace(p))
				if err != nil {
					a, err2 := netip.ParseAddr(strings.TrimSpace(p))
					if err2 != nil {
						return nil, fmt.Errorf("Address: %w", err)
					}
					c.addrs = append(c.addrs, a)
					continue
				}
				c.addrs = append(c.addrs, pf.Addr())
			}
		case "interface.dns":
			for _, p := range strings.Split(v, ",") {
				if a, err := netip.ParseAddr(strings.TrimSpace(p)); err == nil {
					c.dns = append(c.dns, a)
				}
			}
		case "interface.mtu":
			if n, err := strconv.Atoi(v); err == nil && n >= 576 && n <= 1500 {
				c.mtu = n
			}
		case "peer.publickey":
			h, err := b64hex(v)
			if err != nil {
				return nil, fmt.Errorf("PublicKey: %w", err)
			}
			fmt.Fprintf(&c.uapi, "public_key=%s\n", h)
		case "peer.presharedkey":
			h, err := b64hex(v)
			if err != nil {
				return nil, fmt.Errorf("PresharedKey: %w", err)
			}
			fmt.Fprintf(&c.uapi, "preshared_key=%s\n", h)
		case "peer.endpoint":
			ep, err := resolveEndpoint(v)
			if err != nil {
				return nil, fmt.Errorf("Endpoint: %w", err)
			}
			fmt.Fprintf(&c.uapi, "endpoint=%s\n", ep)
		case "peer.allowedips":
			for _, p := range strings.Split(v, ",") {
				p = strings.TrimSpace(p)
				if p != "" {
					fmt.Fprintf(&c.uapi, "allowed_ip=%s\n", p)
				}
			}
		case "peer.persistentkeepalive":
			if n, err := strconv.Atoi(v); err == nil && n > 0 {
				fmt.Fprintf(&c.uapi, "persistent_keepalive_interval=%d\n", n)
			}
		}
	}
	if !strings.Contains(c.uapi.String(), "persistent_keepalive_interval=") {
		c.uapi.WriteString("persistent_keepalive_interval=25\n")
	}
	if len(c.addrs) == 0 || !c.hasPeer || !strings.Contains(c.uapi.String(), "private_key=") || !strings.Contains(c.uapi.String(), "endpoint=") {
		return nil, errors.New("в конфиге нужны PrivateKey, Address, PublicKey и Endpoint")
	}
	return c, nil
}

func resolveEndpoint(v string) (string, error) {
	host, port, err := net.SplitHostPort(v)
	if err != nil {
		return "", err
	}
	if _, err := netip.ParseAddr(host); err == nil {
		return v, nil
	}
	ctx, cancel := context.WithTimeout(context.Background(), 8*time.Second)
	defer cancel()
	ips, err := net.DefaultResolver.LookupNetIP(ctx, "ip4", host)
	if err != nil || len(ips) == 0 {
		return "", fmt.Errorf("не удалось найти %s", host)
	}
	return net.JoinHostPort(ips[0].String(), port), nil
}

func handshaken(dev *device.Device) bool {
	s, err := dev.IpcGet()
	if err != nil {
		return false
	}
	for _, l := range strings.Split(s, "\n") {
		if v, ok := strings.CutPrefix(l, "last_handshake_time_sec="); ok && strings.TrimSpace(v) != "0" {
			return true
		}
	}
	return false
}

type closeWriter interface{ CloseWrite() error }

func pipe(dst, src net.Conn, done chan<- struct{}) {
	if _, err := io.Copy(dst, src); err != nil {
		dst.Close()
		src.Close()
	} else if cw, ok := dst.(closeWriter); ok {
		cw.CloseWrite()
	} else {
		dst.Close()
	}
	done <- struct{}{}
}

func tunnel(c *wgConf, listen, target string, ready func(addr string)) error {
	tdev, tnet, err := netstack.CreateNetTUN(c.addrs, c.dns, c.mtu)
	if err != nil {
		return err
	}
	dev := device.NewDevice(tdev, conn.NewDefaultBind(), device.NewLogger(device.LogLevelError, "wg: "))
	defer dev.Close()
	if err := dev.IpcSet(c.uapi.String()); err != nil {
		return err
	}
	if err := dev.Up(); err != nil {
		return err
	}
	ln, err := net.Listen("tcp", listen)
	if err != nil {
		return err
	}
	defer ln.Close()
	go func() {
		ctx, cancel := context.WithTimeout(context.Background(), 8*time.Second)
		defer cancel()
		if o, err := tnet.DialContext(ctx, "tcp", target); err == nil {
			o.Close()
		}
	}()
	for i := 0; !handshaken(dev); i++ {
		if i >= 80 {
			return errors.New("нет ответа от VPN-сервера: проверьте конфиг, Endpoint и UDP-порт")
		}
		time.Sleep(100 * time.Millisecond)
	}
	ready(ln.Addr().String())
	for {
		in, err := ln.Accept()
		if err != nil {
			return nil
		}
		go func() {
			defer in.Close()
			ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
			out, err := tnet.DialContext(ctx, "tcp", target)
			cancel()
			if err != nil {
				return
			}
			defer out.Close()
			done := make(chan struct{}, 2)
			go pipe(out, in, done)
			go pipe(in, out, done)
			<-done
			<-done
		}()
	}
}

func main() {
	if len(os.Args) != 4 {
		fmt.Fprintln(os.Stderr, "usage: kino-vpn <conf> <listen host:port> <target host:port>")
		os.Exit(2)
	}
	go func() {
		io.Copy(io.Discard, os.Stdin)
		os.Exit(0)
	}()
	f, err := os.Open(os.Args[1])
	if err != nil {
		fmt.Fprintln(os.Stderr, "error:", err)
		os.Exit(1)
	}
	c, err := parse(f)
	f.Close()
	if err == nil {
		err = tunnel(c, os.Args[2], os.Args[3], func(addr string) { fmt.Println("ready", addr) })
	}
	if err != nil {
		fmt.Fprintln(os.Stderr, "error:", err)
		os.Exit(1)
	}
}
