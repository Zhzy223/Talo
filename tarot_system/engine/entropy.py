import hashlib
import os
import secrets
import struct
import threading
import time
from typing import List


class EntropyPool:
    """混合多源熵，输出32字节种子。"""

    def __init__(self, question: str, deterministic: bool = False) -> None:
        self._question = question
        self._timings: List[int] = []
        self._deterministic = deterministic

    def add_timing(self, ns: int) -> None:
        """添加一次按键间隔的纳秒时间。"""
        self._timings.append(ns)

    def collect(
        self,
        use_physical: bool = False,
        shuffle_duration_ms: int = 0,
        shuffle_count: int = 0,
    ) -> bytes:
        """收集并混合所有熵源，返回32字节种子。"""
        if self._deterministic:
            return hashlib.sha256(self._question.encode("utf-8")).digest()

        parts: List[bytes] = [
            secrets.token_bytes(32),
            hashlib.sha256(self._question.encode("utf-8")).digest(),
        ]
        for t in self._timings:
            parts.append(struct.pack("<Q", t & 0xFFFFFFFFFFFFFFFF))

        if use_physical:
            phys = PhysicalRNG()
            parts.append(phys._refill_pool(32))
            mic = try_microphone_entropy()
            if mic:
                parts.append(mic)

        if shuffle_duration_ms > 0 or shuffle_count > 0:
            parts.append(struct.pack("<I", shuffle_duration_ms))
            parts.append(struct.pack("<I", shuffle_count))

        mixed = b"".join(parts)
        return hashlib.sha256(mixed).digest()

    def get_seed(self) -> bytes:
        """向后兼容的别名。"""
        return self.collect()


class _LCG64:
    """简单的64位LCG，用于内部伪随机数生成。"""

    def __init__(self, seed: bytes) -> None:
        self._state = int.from_bytes(seed, "big")

    def next(self) -> int:
        self._state = (
            self._state * 6364136223846793005 + 1442695040888963407
        ) & ((1 << 64) - 1)
        return self._state

    def random(self) -> float:
        return self.next() / (1 << 64)

    def randbelow(self, n: int) -> int:
        if n <= 0:
            raise ValueError("n must be > 0")
        mask = (1 << (n - 1).bit_length()) - 1
        while True:
            val = self.next() & mask
            if val < n:
                return val


class SecureRNG:
    """基于自定义种子的安全随机数生成器，不依赖 random 模块。"""

    def __init__(self, seed: bytes) -> None:
        self._lcg = _LCG64(seed)

    def shuffle(self, lst: list) -> None:
        for i in range(len(lst) - 1, 0, -1):
            j = self._lcg.randbelow(i + 1)
            lst[i], lst[j] = lst[j], lst[i]

    def randbelow(self, n: int) -> int:
        return self._lcg.randbelow(n)

    def randbool(self, p: float = 0.125) -> bool:
        return self._lcg.random() < p


class PhysicalRNG:
    """跨平台硬件熵随机数生成器。"""

    def __init__(self, source: str = "hardware") -> None:
        self._source = source
        self._pool = b""
        self._pool_idx = 0

    def _refill_pool(self, n: int) -> bytes:
        """从操作系统获取硬件级随机字节。"""
        if hasattr(os, "getrandom") and hasattr(os, "GRND_RANDOM"):
            try:
                return os.getrandom(n, os.GRND_RANDOM)
            except (OSError, AttributeError):
                pass
        return os.urandom(n)

    def _consume(self, n: int) -> bytes:
        """从内部池消耗 n 字节，不足时补充。"""
        if self._pool_idx + n > len(self._pool):
            self._pool = self._refill_pool(max(64, n))
            self._pool_idx = 0
        result = self._pool[self._pool_idx : self._pool_idx + n]
        self._pool_idx += n
        return result

    def randbelow(self, n: int) -> int:
        if n <= 0:
            raise ValueError("n must be > 0")
        mask = (1 << (n - 1).bit_length()) - 1
        while True:
            val = int.from_bytes(self._consume(4), "little") & mask
            if val < n:
                return val

    def randbool(self, p: float = 0.5) -> bool:
        if p <= 0:
            return False
        if p >= 1:
            return True
        threshold = int(p * 256)
        return self._consume(1)[0] < threshold

    def shuffle(self, lst: list) -> None:
        for i in range(len(lst) - 1, 0, -1):
            j = self.randbelow(i + 1)
            lst[i], lst[j] = lst[j], lst[i]


def try_microphone_entropy(duration_ms: int = 50) -> bytes | None:
    """尝试从麦克风噪声中提取熵。未安装 pyaudio 时返回 None。"""
    try:
        import pyaudio
        import struct as st
    except ImportError:
        return None

    try:
        pa = pyaudio.PyAudio()
        rate = int(pa.get_default_input_device_info().get("defaultSampleRate", 44100))
        chunk = int(rate * duration_ms / 1000)

        stream = pa.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=rate,
            input=True,
            frames_per_buffer=chunk,
        )
        data = stream.read(chunk, exception_on_overflow=False)
        stream.stop_stream()
        stream.close()
        pa.terminate()

        samples = st.unpack(f"<{len(data) // 2}h", data)
        # 提取每个样本的 LSB，每 8 个 bit 打包成一个字节
        lsb_bits = [sample & 1 for sample in samples]
        result = bytearray()
        for i in range(0, len(lsb_bits) - 7, 8):
            byte = 0
            for j in range(8):
                byte |= lsb_bits[i + j] << j
            result.append(byte)
        return bytes(result)
    except Exception:
        return None
