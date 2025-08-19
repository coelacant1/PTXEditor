#!/usr/bin/env python3
import argparse, mmap, os, struct, time
import numpy as np
import matplotlib.pyplot as plt

HDR_FMT = "<I H H I I I I I"   # magic,u16 version,u16 fmt,u32 w,h,stride,bufcnt,active
HDR_SIZE = struct.calcsize(HDR_FMT)
MAGIC = 0x55434642  # 'UCFB'

BUF_HDR_FMT = "<Q"  # std::atomic<uint64_t> seq (we'll read it as u64)
BUF_HDR_SIZE = struct.calcsize(BUF_HDR_FMT)

def open_mmap(path):
    fd = os.open(path, os.O_RDWR)
    try:
        size = os.stat(path).st_size
        mm = mmap.mmap(fd, size, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE)
        return mm, size
    finally:
        os.close(fd)

def read_header(mm):
    hdr = mm[:HDR_SIZE]
    magic, ver, fmt_, w, h, stride, bufcnt, active = struct.unpack(HDR_FMT, hdr)
    if magic != MAGIC:
        raise RuntimeError(f"Bad magic: 0x{magic:08x}")
    if fmt_ != 0:
        raise RuntimeError(f"Unsupported pixel format {fmt_} (expected 0=RGB888)")
    return dict(ver=ver, fmt=fmt_, w=w, h=h, stride=stride, bufcnt=bufcnt, active=active)

def buffer_offset(i, h, stride):
    one = BUF_HDR_SIZE + (h * stride)
    return HDR_SIZE + i * one

def buf_payload_view(mm, i, h, stride):
    off = buffer_offset(i, h, stride)
    seq = struct.unpack_from(BUF_HDR_FMT, mm, off)[0]
    payload_off = off + BUF_HDR_SIZE
    payload = memoryview(mm)[payload_off:payload_off + (h * stride)]
    return seq, payload

def choose_latest_ready(mm, hdr):
    for candidate in [hdr["active"]] + [i for i in range(hdr["bufcnt"]) if i != hdr["active"]]:
        seq, payload = buf_payload_view(mm, candidate, hdr["h"], hdr["stride"])
        if seq & 1:
            return candidate, seq, payload
    return None, None, None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fb", default="/dev/shm/uc3d_fb", help="Path to frame buffer SHM file")
    ap.add_argument("--fps", type=float, default=60.0, help="Viewer refresh rate")
    args = ap.parse_args()

    mm, _ = open_mmap(args.fb)
    hdr = read_header(mm)
    print(f"Connected: {hdr['w']}x{hdr['h']} RGB888, stride={hdr['stride']}, buffers={hdr['bufcnt']}")

    plt.ion()
    fig, ax = plt.subplots()
    img = ax.imshow(np.zeros((hdr["h"], hdr["w"], 3), dtype=np.uint8), vmin=0, vmax=255)
    ax.axis("off")
    fig.canvas.manager.set_window_title("uCore3D viewer")

    last_seq = None
    period = 1.0 / max(1e-3, args.fps)
    try:
        while True:
            hdr = read_header(mm)
            idx, seq, payload = choose_latest_ready(mm, hdr)
            if payload is not None and seq != last_seq:
                # Convert RGB888 (top-left origin expected by viewer)
                arr = np.frombuffer(payload, dtype=np.uint8).reshape(hdr["h"], hdr["stride"])
                rgb = arr[:, :hdr["w"]*3].reshape(hdr["h"], hdr["w"], 3)
                img.set_data(rgb)
                fig.canvas.draw_idle()
                last_seq = seq
            plt.pause(0.001)
            time.sleep(period)
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()
