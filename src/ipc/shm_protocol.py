import mmap
import os
import struct
from multiprocessing import shared_memory

FMT_RGB888 = 0
VERSION = 1

FB_HDR = struct.Struct("<I H H I I I I I")  # 28 bytes
SEQ64  = struct.Struct("<Q")
MAGIC  = 0x55434642  # 'UCFB'

FB_SHM_NAME   = os.getenv("UC3D_FB_NAME", "uc3d_fb")
CTRL_SHM_NAME = os.getenv("UC3D_CTRL_NAME", "uc3d_ctrl")

FB_HEADER_STRUCT = struct.Struct("<I H H I I I I I")  # magic,version,format,w,h,stride,bufcnt,active
SEQ_STRUCT = struct.Struct("<Q")  # uint64 sequence

REG_HDR = struct.Struct("<I I I")  # magic, version, cam_count
REG_CAM = struct.Struct("<32s I I I I")  # name[32], index, pixel_count, width, height
REG_MAGIC = 0x55435247

class RegistryReader:
    def __init__(self, name="/uc3d_reg"):
        self.name = name
        self.fd = None
        self.mm = None

    def connect(self):
        path = f"/dev/shm{self.name}"
        self.fd = os.open(path, os.O_RDONLY)
        st = os.fstat(self.fd)
        self.mm = mmap.mmap(self.fd, st.st_size, mmap.MAP_SHARED, mmap.PROT_READ)

    def list_cameras(self):
        if not self.mm: return []
        magic, ver, count = REG_HDR.unpack_from(self.mm, 0)
        if magic != REG_MAGIC: return []
        cams = []
        off = REG_HDR.size
        for _ in range(count):
            name_b, idx, N, W, H = REG_CAM.unpack_from(self.mm, off)
            off += REG_CAM.size
            name = name_b.split(b'\x00',1)[0].decode('utf-8', 'ignore')
            cams.append({"name": name, "index": idx, "count": N, "width": W, "height": H})
        return cams

    def close(self):
        if self.mm: self.mm.close()
        if self.fd is not None: os.close(self.fd)
        self.mm = None; self.fd = None

class FrameShmReader:
    def __init__(self, name="/uc3d_fb"):
        self.name = name
        self.fd = None
        self.mm = None
        self.width = 0
        self.height = 0
        self.stride = 0
        self.bufcnt = 0
        self.header_size = FB_HDR.size     # 28
        self.onebuf_size = 0
        self._last_seq = 0

    def _path(self):
        # mmap by filesystem path
        return f"/dev/shm{self.name}" if self.name.startswith("/") else f"/dev/shm/{self.name}"

    def connect(self):
        path = self._path()
        self.fd = os.open(path, os.O_RDONLY)
        st = os.fstat(self.fd)
        self.mm = mmap.mmap(self.fd, st.st_size, mmap.MAP_SHARED, mmap.PROT_READ)

        header = self.mm[:self.header_size]
        (magic, ver, fmt, w, h, stride, bufcnt, active) = FB_HDR.unpack(header)
        if magic != MAGIC:
            raise RuntimeError(f"Bad FB magic: 0x{magic:08X}")
        self.width = w; self.height = h; self.stride = stride; self.bufcnt = bufcnt
        self.onebuf_size = 8 + (h * stride)  # 8 = seq

    def _buf_base(self, idx):
        return self.header_size + idx * self.onebuf_size

    def latest_frame_view(self, max_spins=64, sleep_ns=0):
        """Return (memoryview, seq) or (None, last_seq). Non-blocking-ish with small bounded spin."""
        if self.mm is None:
            return (None, self._last_seq)

        # active_index is the last uint32 in header at offset 24
        active = struct.unpack_from("<I", self.mm, 24)[0]
        base   = self._buf_base(active)

        def read_seq():
            return SEQ64.unpack_from(self.mm, base)[0]

        spins = 0
        while spins < max_spins:
            s1 = read_seq()
            if (s1 & 1) == 1:  # odd => ready
                if sleep_ns: time.sleep(sleep_ns * 1e-9)
                s2 = read_seq()
                if s1 == s2:
                    payload_off = base + 8
                    payload_len = self.height * self.stride
                    mv = memoryview(self.mm)[payload_off: payload_off + payload_len]
                    self._last_seq = s1
                    return (mv, s1)
            spins += 1
            if sleep_ns: time.sleep(sleep_ns * 1e-9)

        return (None, self._last_seq)
    
    def latest_frame_view_fast(self):
        """Return (view, seq) immediately or (None, last_seq) if not ready."""
        if self.mm is None:
            return (None, self._last_seq)

        # active_index is the last uint32 in the 28-byte header -> offset 24
        active_idx = struct.unpack_from("<I", self.mm, 24)[0]
        base = self.header_size + active_idx * self.onebuf_size

        # seq at start of buffer
        seq = struct.unpack_from("<Q", self.mm, base)[0]
        if (seq & 1) == 0:  # even = writer in progress
            return (None, self._last_seq)

        payload_off = base + 8
        payload_len = self.height * self.stride
        mv = memoryview(self.mm)[payload_off: payload_off + payload_len]
        self._last_seq = seq
        return (mv, seq)

    def close(self):
        try:
            if self.mm: self.mm.close()
            if self.fd is not None:
                os.close(self.fd)
        finally:
            self.mm = None
            self.fd = None

class CtrlShmWriter:
    CTRL_STRUCT = struct.Struct("<Q B x x x f 3f 3f 3f I")  
    # seq, pause (1B) + 3x pad, dt_scale, cam_pos[3], cam_look[3], cam_up[3], debug_flags

    def __init__(self, name=CTRL_SHM_NAME):
        self.name = name
        self.shm = None
        self.seq = 0
        # defaults
        self.pause = 0
        self.dt_scale = 1.0
        self.cam_pos = [0.0,0.0,0.0]
        self.cam_look = [0.0,0.0,-1.0]
        self.cam_up = [0.0,1.0,0.0]
        self.debug_flags = 0

    def connect(self):
        self.shm = shared_memory.SharedMemory(name=self.name)

    def write(self):
        self.seq += 1
        buf = self.CTRL_STRUCT.pack(
            self.seq, self.pause, self.dt_scale,
            *self.cam_pos, *self.cam_look, *self.cam_up,
            self.debug_flags
        )
        self.shm.buf[:self.CTRL_STRUCT.size] = buf

    def close(self):
        if self.shm:
            self.shm.close()
            self.shm = None

class GeoShmReader:
    def __init__(self, name="/uc3d_geom"):
        self.name = name            # POSIX shm name (e.g. "/uc3d_geom")
        self.fd = None
        self.mm = None
        self.count = 0
        self.width = 0
        self.height = 0
        self._last_seq = 0
        self._hdr_size = 24         # magic(4)+count(4)+width(4)+height(4)+seq(8)

    def connect(self):
        # open under /dev/shm
        path = f"/dev/shm{self.name}"
        self.fd = os.open(path, os.O_RDONLY)
        st = os.fstat(self.fd)
        self.mm = mmap.mmap(self.fd, st.st_size, mmap.MAP_SHARED, mmap.PROT_READ)

        magic, count, width, height = struct.unpack_from("<IIII", self.mm, 0)
        if magic != 0x5543474D:  # 'UCGM'
            raise RuntimeError(f"Bad GEOM magic: 0x{magic:08X}")
        self.count  = count
        self.width  = width
        self.height = height

    def latest(self, max_spins=200, sleep_ns=0):
        if self.mm is None:
            return (None, None, self._last_seq)

        def _seq():
            # seq at offset 16 (after 4*4 bytes)
            return struct.unpack_from("<Q", self.mm, 16)[0]

        spins = 0
        while spins < max_spins:
            s1 = _seq()
            if (s1 & 1) == 1:                 # odd = ready
                if sleep_ns: time.sleep(sleep_ns * 1e-9)
                s2 = _seq()
                if s1 == s2:                  # stable
                    payload = memoryview(self.mm)[self._hdr_size : self._hdr_size + self.count * 8]
                    self._last_seq = s1
                    meta = {"count": self.count, "width": self.width, "height": self.height}
                    return (payload, meta, s1)
            spins += 1
            if sleep_ns: time.sleep(sleep_ns * 1e-9)

        return (None, None, self._last_seq)
    
    def latest_fast(self):
        """Return (xy_view, meta, seq) immediately or (None, None, last_seq)."""
        if self.mm is None:
            return (None, None, self._last_seq)

        seq = struct.unpack_from("<Q", self.mm, 16)[0]
        if (seq & 1) == 0:                   # even = writer in progress
            return (None, None, self._last_seq)

        payload = memoryview(self.mm)[self._hdr_size : self._hdr_size + self.count * 8]
        self._last_seq = seq
        meta = {"count": self.count, "width": self.width, "height": self.height}
        return (payload, meta, seq)
    
    def close(self):
        try:
            if self.mm:
                self.mm.close()
            if self.fd is not None:
                os.close(self.fd)
        finally:
            self.mm = None
            self.fd = None
