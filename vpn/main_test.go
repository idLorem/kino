package main

import (
	"crypto/rand"
	"encoding/base64"
	"encoding/hex"
	"io"
	"net"
	"net/http"
	"net/netip"
	"strings"
	"testing"
	"time"

	"golang.org/x/crypto/curve25519"
	"golang.zx2c4.com/wireguard/conn"
	"golang.zx2c4.com/wireguard/device"
	"golang.zx2c4.com/wireguard/tun/netstack"
)

const sample = `[Interface]
PrivateKey = AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=
Address = 10.8.0.2/24
DNS = 10.8.0.1
[Peer]
PublicKey = AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=
AllowedIPs = 10.8.0.0/24, 192.168.1.0/24
Endpoint = 203.0.113.5:51820
PersistentKeepalive = 25
`

func TestParse(t *testing.T) {
	c, err := parse(strings.NewReader(sample))
	if err != nil {
		t.Fatal(err)
	}
	u := c.uapi.String()
	for _, w := range []string{"private_key=0000", "endpoint=203.0.113.5:51820", "allowed_ip=192.168.1.0/24", "persistent_keepalive_interval=25"} {
		if !strings.Contains(u, w) {
			t.Fatal("missing", w, u)
		}
	}
	if len(c.addrs) != 1 || c.addrs[0].String() != "10.8.0.2" {
		t.Fatal(c.addrs)
	}
	if _, err := parse(strings.NewReader("[Interface]\n")); err == nil {
		t.Fatal("empty conf accepted")
	}
}

func TestTunnel(t *testing.T) {
	var sk, ck [32]byte
	rand.Read(sk[:])
	rand.Read(ck[:])
	spub, _ := curve25519.X25519(sk[:], curve25519.Basepoint)
	cpub, _ := curve25519.X25519(ck[:], curve25519.Basepoint)
	e := base64.StdEncoding.EncodeToString
	h := hex.EncodeToString

	stun, snet, err := netstack.CreateNetTUN([]netip.Addr{netip.MustParseAddr("10.9.0.1")}, nil, 1280)
	if err != nil {
		t.Fatal(err)
	}
	sdev := device.NewDevice(stun, conn.NewDefaultBind(), device.NewLogger(device.LogLevelError, ""))
	defer sdev.Close()
	if err := sdev.IpcSet("private_key=" + h(sk[:]) + "\nlisten_port=51999\npublic_key=" + h(cpub) + "\nallowed_ip=10.9.0.2/32\n"); err != nil {
		t.Fatal(err)
	}
	sdev.Up()
	sl, err := snet.ListenTCP(&net.TCPAddr{Port: 8080})
	if err != nil {
		t.Fatal(err)
	}
	go http.Serve(sl, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { w.Write([]byte("hello-through-vpn")) }))

	cfg := "[Interface]\nPrivateKey = " + e(ck[:]) + "\nAddress = 10.9.0.2/24\n[Peer]\nPublicKey = " + e(spub) + "\nAllowedIPs = 10.9.0.0/24\nEndpoint = 127.0.0.1:51999\nPersistentKeepalive = 1\n"
	c, err := parse(strings.NewReader(cfg))
	if err != nil {
		t.Fatal(err)
	}
	ready := make(chan string, 1)
	go tunnel(c, "127.0.0.1:0", "10.9.0.1:8080", func(a string) { ready <- a })
	var addr string
	select {
	case addr = <-ready:
	case <-time.After(15 * time.Second):
		t.Fatal("no handshake")
	}
	cl := http.Client{Timeout: 15 * time.Second}
	resp, err := cl.Get("http://" + addr + "/")
	if err != nil {
		t.Fatal(err)
	}
	b, _ := io.ReadAll(resp.Body)
	if string(b) != "hello-through-vpn" {
		t.Fatal(string(b))
	}
}

func TestNoHandshake(t *testing.T) {
	var ck, sk [32]byte
	rand.Read(ck[:])
	rand.Read(sk[:])
	spub, _ := curve25519.X25519(sk[:], curve25519.Basepoint)
	e := base64.StdEncoding.EncodeToString
	cfg := "[Interface]\nPrivateKey = " + e(ck[:]) + "\nAddress = 10.9.0.2/24\n[Peer]\nPublicKey = " + e(spub) + "\nAllowedIPs = 10.9.0.0/24\nEndpoint = 127.0.0.1:51998\n"
	c, err := parse(strings.NewReader(cfg))
	if err != nil {
		t.Fatal(err)
	}
	if err := tunnel(c, "127.0.0.1:0", "10.9.0.1:8080", func(string) { t.Fatal("ready without handshake") }); err == nil {
		t.Fatal("expected error")
	}
}
