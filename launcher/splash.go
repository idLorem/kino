//go:build windows

package main

import (
	"bytes"
	_ "embed"
	"image/png"
	"math"
	"runtime"
	"strings"
	"syscall"
	"time"
	"unsafe"
)

//go:embed logo.png
var logoPNG []byte

var (
	gdi32                   = syscall.NewLazyDLL("gdi32.dll")
	kernel32                = syscall.NewLazyDLL("kernel32.dll")
	pSetProcessDPIAware     = user32.NewProc("SetProcessDPIAware")
	pGetDpiForSystem        = user32.NewProc("GetDpiForSystem")
	pGetSystemMetrics       = user32.NewProc("GetSystemMetrics")
	pSystemParametersInfoW  = user32.NewProc("SystemParametersInfoW")
	pRegisterClassExW       = user32.NewProc("RegisterClassExW")
	pCreateWindowExW        = user32.NewProc("CreateWindowExW")
	pDefWindowProcW         = user32.NewProc("DefWindowProcW")
	pDestroyWindow          = user32.NewProc("DestroyWindow")
	pShowWindow             = user32.NewProc("ShowWindow")
	pUpdateLayeredWindow    = user32.NewProc("UpdateLayeredWindow")
	pPeekMessageW           = user32.NewProc("PeekMessageW")
	pTranslateMessage       = user32.NewProc("TranslateMessage")
	pDispatchMessageW       = user32.NewProc("DispatchMessageW")
	pFindWindowExW          = user32.NewProc("FindWindowExW")
	pGetClassNameW          = user32.NewProc("GetClassNameW")
	pIsWindowVisible        = user32.NewProc("IsWindowVisible")
	pGetDC                  = user32.NewProc("GetDC")
	pReleaseDC              = user32.NewProc("ReleaseDC")
	pCreateCompatibleDC     = gdi32.NewProc("CreateCompatibleDC")
	pCreateDIBSection       = gdi32.NewProc("CreateDIBSection")
	pSelectObject           = gdi32.NewProc("SelectObject")
	pDeleteObject           = gdi32.NewProc("DeleteObject")
	pDeleteDC               = gdi32.NewProc("DeleteDC")
	pGetModuleHandleW       = kernel32.NewProc("GetModuleHandleW")
)

type wndClassEx struct {
	cbSize        uint32
	style         uint32
	lpfnWndProc   uintptr
	cbClsExtra    int32
	cbWndExtra    int32
	hInstance     uintptr
	hIcon         uintptr
	hCursor       uintptr
	hbrBackground uintptr
	lpszMenuName  *uint16
	lpszClassName *uint16
	hIconSm       uintptr
}

type bitmapInfoHeader struct {
	biSize          uint32
	biWidth         int32
	biHeight        int32
	biPlanes        uint16
	biBitCount      uint16
	biCompression   uint32
	biSizeImage     uint32
	biXPelsPerMeter int32
	biYPelsPerMeter int32
	biClrUsed       uint32
	biClrImportant  uint32
}

type winMsg struct {
	hwnd    uintptr
	message uint32
	wParam  uintptr
	lParam  uintptr
	time    uint32
	pt      [2]int32
	private uint32
}

type splash struct {
	done chan struct{}
	stop chan struct{}
}

func startSplash() *splash {
	s := &splash{done: make(chan struct{}), stop: make(chan struct{}, 1)}
	go s.run()
	return s
}

func (s *splash) close() {
	if s == nil {
		return
	}
	select {
	case s.stop <- struct{}{}:
	default:
	}
	<-s.done
}

func drawSplash(scale float64) (int, int, []byte) {
	w, h := int(320*scale), int(220*scale)
	buf := make([]byte, w*h*4)
	rad := 28 * scale
	const pr, pg, pb, pa = 12.0, 12.0, 14.0, 238.0
	for y := 0; y < h; y++ {
		for x := 0; x < w; x++ {
			cx := math.Max(math.Max(rad-float64(x)-0.5, float64(x)+0.5-(float64(w)-rad)), 0)
			cy := math.Max(math.Max(rad-float64(y)-0.5, float64(y)+0.5-(float64(h)-rad)), 0)
			cov := math.Min(math.Max(rad-math.Hypot(cx, cy)+0.5, 0), 1)
			a := pa / 255 * cov
			i := (y*w + x) * 4
			buf[i], buf[i+1], buf[i+2], buf[i+3] = byte(pb*a), byte(pg*a), byte(pr*a), byte(255*a)
		}
	}
	img, err := png.Decode(bytes.NewReader(logoPNG))
	if err != nil {
		return w, h, buf
	}
	b := img.Bounds()
	lw := int(180 * scale)
	lh := lw * b.Dy() / b.Dx()
	ox, oy := (w-lw)/2, (h-lh)/2
	alpha := func(px, py int) float64 {
		_, _, _, a := img.At(px, py).RGBA()
		return float64(a) / 65535
	}
	sx, sy := float64(b.Dx())/float64(lw), float64(b.Dy())/float64(lh)
	for y := 0; y < lh; y++ {
		for x := 0; x < lw; x++ {
			x0, y0 := int(float64(x)*sx), int(float64(y)*sy)
			x1, y1 := int(float64(x+1)*sx), int(float64(y+1)*sy)
			sum, n := 0.0, 0
			for yy := y0; yy < y1 && yy < b.Dy(); yy++ {
				for xx := x0; xx < x1 && xx < b.Dx(); xx++ {
					sum += alpha(b.Min.X+xx, b.Min.Y+yy)
					n++
				}
			}
			if n == 0 {
				continue
			}
			la := sum / float64(n)
			i := ((oy+y)*w + ox + x) * 4
			for c := 0; c < 3; c++ {
				buf[i+c] = byte(float64(buf[i+c])*(1-la) + 240*la)
			}
			buf[i+3] = byte(float64(buf[i+3])*(1-la) + 255*la)
		}
	}
	return w, h, buf
}

func appWindowVisible() bool {
	title := u16("Kino")
	buf := make([]uint16, 64)
	var h uintptr
	for {
		h, _, _ = pFindWindowExW.Call(0, h, 0, uintptr(unsafe.Pointer(title)))
		if h == 0 {
			return false
		}
		pGetClassNameW.Call(h, uintptr(unsafe.Pointer(&buf[0])), 64)
		if strings.HasPrefix(syscall.UTF16ToString(buf), "WindowsForms") {
			if v, _, _ := pIsWindowVisible.Call(h); v != 0 {
				return true
			}
		}
	}
}

func (s *splash) run() {
	defer close(s.done)
	runtime.LockOSThread()
	defer runtime.UnlockOSThread()
	pSetProcessDPIAware.Call()
	dpi := uintptr(96)
	if pGetDpiForSystem.Find() == nil {
		if d, _, _ := pGetDpiForSystem.Call(); d > 0 {
			dpi = d
		}
	}
	w, h, px := drawSplash(float64(dpi) / 96)
	var wa [4]int32
	pSystemParametersInfoW.Call(0x30, 0, uintptr(unsafe.Pointer(&wa)), 0)
	capH, _, _ := pGetSystemMetrics.Call(4)
	cx := int(wa[0]+wa[2])/2 - w/2
	cy := int(wa[1]+wa[3])/2 - h/2 + int(capH)/2

	hinst, _, _ := pGetModuleHandleW.Call(0)
	cls := u16("KinoSplash")
	wc := wndClassEx{lpfnWndProc: syscall.NewCallback(func(hwnd, msg, wp, lp uintptr) uintptr {
		r, _, _ := pDefWindowProcW.Call(hwnd, msg, wp, lp)
		return r
	}), hInstance: hinst, lpszClassName: cls}
	wc.cbSize = uint32(unsafe.Sizeof(wc))
	pRegisterClassExW.Call(uintptr(unsafe.Pointer(&wc)))
	hwnd, _, _ := pCreateWindowExW.Call(0x00080000|0x00000080|0x00000008|0x08000000,
		uintptr(unsafe.Pointer(cls)), uintptr(unsafe.Pointer(u16("Kino splash"))), 0x80000000,
		uintptr(cx), uintptr(cy), uintptr(w), uintptr(h), 0, 0, hinst, 0)
	if hwnd == 0 {
		return
	}
	defer pDestroyWindow.Call(hwnd)

	screen, _, _ := pGetDC.Call(0)
	defer pReleaseDC.Call(0, screen)
	mem, _, _ := pCreateCompatibleDC.Call(screen)
	defer pDeleteDC.Call(mem)
	bi := bitmapInfoHeader{biWidth: int32(w), biHeight: -int32(h), biPlanes: 1, biBitCount: 32}
	bi.biSize = uint32(unsafe.Sizeof(bi))
	var bits unsafe.Pointer
	bmp, _, _ := pCreateDIBSection.Call(mem, uintptr(unsafe.Pointer(&bi)), 0, uintptr(unsafe.Pointer(&bits)), 0, 0)
	if bmp == 0 {
		return
	}
	defer pDeleteObject.Call(bmp)
	copy(unsafe.Slice((*byte)(bits), len(px)), px)
	pSelectObject.Call(mem, bmp)

	pos := [2]int32{int32(cx), int32(cy)}
	size := [2]int32{int32(w), int32(h)}
	src := [2]int32{0, 0}
	paint := func(a float64) {
		blend := uint32(byte(math.Round(math.Min(math.Max(a, 0), 1)*255)))<<16 | 1<<24
		pUpdateLayeredWindow.Call(hwnd, screen, uintptr(unsafe.Pointer(&pos)), uintptr(unsafe.Pointer(&size)),
			mem, uintptr(unsafe.Pointer(&src)), 0, uintptr(unsafe.Pointer(&blend)), 2)
	}
	paint(0)
	pShowWindow.Call(hwnd, 4)

	pump := func() {
		var m winMsg
		for {
			r, _, _ := pPeekMessageW.Call(uintptr(unsafe.Pointer(&m)), 0, 0, 0, 1)
			if r == 0 {
				return
			}
			pTranslateMessage.Call(uintptr(unsafe.Pointer(&m)))
			pDispatchMessageW.Call(uintptr(unsafe.Pointer(&m)))
		}
	}
	ease := func(t float64) float64 { return 1 - math.Pow(1-t, 3) }
	const fade = 450 * time.Millisecond
	start := time.Now()
	stopped := false
	for {
		pump()
		el := time.Since(start)
		if el < fade {
			paint(ease(float64(el) / float64(fade)))
		} else {
			paint(1)
		}
		select {
		case <-s.stop:
			stopped = true
		default:
		}
		if el >= fade+400*time.Millisecond && (stopped || appWindowVisible() || el > 8*time.Second) {
			break
		}
		time.Sleep(15 * time.Millisecond)
	}
	out := time.Now()
	for {
		pump()
		t := float64(time.Since(out)) / float64(fade)
		if t >= 1 {
			break
		}
		paint(1 - ease(t))
		time.Sleep(15 * time.Millisecond)
	}
}
