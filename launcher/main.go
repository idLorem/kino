//go:build windows

package main

import (
	"archive/zip"
	"bytes"
	_ "embed"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"sync"
	"syscall"
	"time"
	"unsafe"
)

//go:embed payload.zip
var payload []byte

//go:embed payload.ver
var version string

var (
	user32  = syscall.NewLazyDLL("user32.dll")
	msgBoxW = user32.NewProc("MessageBoxW")
)

func u16(s string) *uint16 { p, _ := syscall.UTF16PtrFromString(s); return p }

func msgBox(text string, icon uintptr) {
	msgBoxW.Call(0, uintptr(unsafe.Pointer(u16(text))), uintptr(unsafe.Pointer(u16("Kino"))), icon|0x10000)
}

func exists(p string) bool {
	_, err := os.Stat(p)
	return err == nil
}

func installNeeded(exeDir string) bool {
	if exists(filepath.Join(exeDir, "kino.installed")) || exists(filepath.Join(exeDir, "kino.portable")) || os.Getenv("KINO_NOINSTALL") != "" {
		return false
	}
	for _, a := range os.Args[1:] {
		if a == "--portable" {
			return false
		}
	}
	return os.Getenv("LOCALAPPDATA") != ""
}

func extract(dst string) error {
	zr, err := zip.NewReader(bytes.NewReader(payload), int64(len(payload)))
	if err != nil {
		return err
	}
	base := filepath.Clean(dst) + string(os.PathSeparator)
	jobs := make(chan *zip.File)
	errs := make(chan error, 16)
	var wg sync.WaitGroup
	for i := 0; i < 8; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for f := range jobs {
				if err := extractOne(dst, f); err != nil {
					select {
					case errs <- err:
					default:
					}
				}
			}
		}()
	}
	for _, f := range zr.File {
		p := filepath.Join(dst, filepath.FromSlash(f.Name))
		if !strings.HasPrefix(p+string(os.PathSeparator), base) && p != filepath.Clean(dst) {
			close(jobs)
			wg.Wait()
			return fmt.Errorf("bad path %s", f.Name)
		}
		if f.FileInfo().IsDir() {
			if err := os.MkdirAll(p, 0o755); err != nil {
				close(jobs)
				wg.Wait()
				return err
			}
			continue
		}
		jobs <- f
	}
	close(jobs)
	wg.Wait()
	select {
	case err := <-errs:
		return err
	default:
	}
	return nil
}

func extractOne(dst string, f *zip.File) error {
	p := filepath.Join(dst, filepath.FromSlash(f.Name))
	if err := os.MkdirAll(filepath.Dir(p), 0o755); err != nil {
		return err
	}
	rc, err := f.Open()
	if err != nil {
		return err
	}
	defer rc.Close()
	out, err := os.Create(p)
	if err != nil {
		return err
	}
	_, err = io.Copy(out, rc)
	if cerr := out.Close(); err == nil {
		err = cerr
	}
	return err
}

func tail(path string, n int) string {
	b, err := os.ReadFile(path)
	if err != nil {
		return ""
	}
	s := strings.TrimSpace(string(b))
	if len(s) > n {
		s = "…" + s[len(s)-n:]
	}
	return s
}

func main() {
	ver := strings.TrimSpace(version)
	exe, _ := os.Executable()
	exeDir := filepath.Dir(exe)
	setup := installNeeded(exeDir)
	local := os.Getenv("LOCALAPPDATA")
	if local == "" {
		local = os.TempDir()
	}
	root := filepath.Join(local, "kino")
	rt := filepath.Join(root, "rt-"+ver)

	if _, err := os.Stat(filepath.Join(rt, ".ok")); err != nil {
		tmp := rt + ".tmp"
		os.RemoveAll(tmp)
		os.RemoveAll(rt)
		err := extract(tmp)
		if err == nil {
			err = os.WriteFile(filepath.Join(tmp, ".ok"), []byte(ver), 0o644)
		}
		if err == nil {
			err = os.Rename(tmp, rt)
		}
		if err != nil {
			msgBox("Не удалось распаковать программу:\n"+err.Error(), 0x10)
			return
		}
		if ents, e := os.ReadDir(root); e == nil {
			for _, en := range ents {
				if en.IsDir() && strings.HasPrefix(en.Name(), "rt-") && en.Name() != "rt-"+ver {
					os.RemoveAll(filepath.Join(root, en.Name()))
				}
			}
		}
	}

	logPath := filepath.Join(exeDir, "kino-error.log")
	lf, err := os.Create(logPath)
	if err != nil {
		os.MkdirAll(root, 0o755)
		logPath = filepath.Join(root, "kino-error.log")
		lf, _ = os.Create(logPath)
	}

	appDir := filepath.Join(root, "app")
	mainPy := filepath.Join(rt, "main.py")
	if b, e := os.ReadFile(filepath.Join(appDir, "base.txt")); e == nil && strings.TrimSpace(string(b)) == ver {
		if _, e2 := os.Stat(filepath.Join(appDir, "main.py")); e2 == nil {
			mainPy = filepath.Join(appDir, "main.py")
		}
	}
	fail := func() {
		msgBox("Kino завершился с ошибкой.\n\n"+tail(logPath, 900)+"\n\nПодробности: "+logPath, 0x10)
	}
	start := func(extra ...string) (chan error, bool) {
		args := append([]string{"-X", "utf8", mainPy}, extra...)
		cmd := exec.Command(filepath.Join(rt, "pythonw.exe"), args...)
		cmd.Dir = exeDir
		env := []string{}
		for _, e := range os.Environ() {
			u := strings.ToUpper(e)
			if strings.HasPrefix(u, "PYTHONHOME=") || strings.HasPrefix(u, "PYTHONPATH=") {
				continue
			}
			env = append(env, e)
		}
		paths := []string{rt, filepath.Join(rt, "DLLs"), filepath.Join(rt, "Library", "bin")}
		env = append(env, "PATH="+strings.Join(paths, ";")+";"+os.Getenv("PATH"), "KINO_DATA_DIR="+exeDir, "KINO_BASE="+ver, "KINO_APP_DIR="+appDir, "KINO_RT="+rt, "KINO_EXE="+exe, "PYTHONNOUSERSITE=1")
		cmd.Env = env
		if lf != nil {
			cmd.Stderr = lf
			cmd.Stdout = lf
		}
		cmd.SysProcAttr = &syscall.SysProcAttr{CreationFlags: 0x08000000}
		if err := cmd.Start(); err != nil {
			msgBox("Не удалось запустить Kino:\n"+err.Error(), 0x10)
			return nil, false
		}
		ch := make(chan error, 1)
		go func() { ch <- cmd.Wait() }()
		return ch, true
	}

	if setup {
		ch, ok := start("--install")
		if !ok {
			return
		}
		code := 0
		if e := <-ch; e != nil {
			code = 1
			if ee, isExit := e.(*exec.ExitError); isExit {
				code = ee.ExitCode()
			}
		}
		switch code {
		case 0, 4:
			return
		case 3:
		default:
			fail()
			return
		}
	}

	sp := startSplash()
	ch, ok := start()
	if !ok {
		sp.close()
		return
	}
	var e error
	select {
	case e = <-ch:
	case <-time.After(15 * time.Second):
	}
	sp.close()
	if e != nil {
		fail()
	}
}
