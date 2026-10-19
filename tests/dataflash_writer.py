"""Minimal ArduPilot DataFlash (.bin) writer for synthetic test logs.

Writes FMT records plus data records in the binary layout pymavlink's DFReader
reads, using the field formats ArduPilot itself logs.
"""

from __future__ import annotations

import struct
from pathlib import Path
from typing import Any

HEAD = b"\xa3\x95"
FMT_ID = 128

# Format char -> (struct code, scale applied to stored ints)
_CODES: dict[str, tuple[str, float | None]] = {
    "b": ("b", None), "B": ("B", None), "h": ("h", None), "H": ("H", None),
    "i": ("i", None), "I": ("I", None), "f": ("f", None), "d": ("d", None),
    "q": ("q", None), "Q": ("Q", None), "M": ("b", None),
    "n": ("4s", None), "N": ("16s", None), "Z": ("64s", None),
    "c": ("h", 0.01), "C": ("H", 0.01), "e": ("i", 0.01), "E": ("I", 0.01),
    "L": ("i", 1e-7),
}  # fmt: skip

# ArduPilot (Copter 4.x) layouts for the messages the parser reads.
FORMATS: dict[str, tuple[str, str]] = {
    "PARM": ("QNf", "TimeUS,Name,Value"),
    "ATT": ("QccccCCCC", "TimeUS,DesRoll,Roll,DesPitch,Pitch,DesYaw,Yaw,ErrRP,ErrYaw"),
    "GPS": ("QBBIHBcLLeffffB", "TimeUS,I,Status,GMS,GWk,NSats,HDop,Lat,Lng,Alt,Spd,GCrs,VZ,Yaw,U"),
    "GPA": ("QBCCCCfBIHH", "TimeUS,I,VDop,HAcc,VAcc,SAcc,YAcc,VV,SMS,Delta,Und"),
    "BAT": ("QBfffffcfBBB", "TimeUS,Inst,Volt,VoltR,Curr,CurrTot,EnrgTot,Temp,Res,RemPct,H,SH"),
    "CURR": ("QffffI", "TimeUS,Volt,VoltR,Curr,CurrTot,Res"),
    "RCOU": ("QHHHHHHHHHHHHHH", "TimeUS," + ",".join(f"C{i}" for i in range(1, 15))),
    "VIBE": ("QBfffI", "TimeUS,IMU,VibeX,VibeY,VibeZ,Clip"),
    "VIBE_OLD": ("QfffIII", "TimeUS,VibeX,VibeY,VibeZ,Clip0,Clip1,Clip2"),
    "CTUN": ("QffffffefhhB", "TimeUS,ThI,ABst,ThO,ThH,DAlt,Alt,BAlt,DSAlt,DCRt,CRt,N"),
    "MODE": ("QMBB", "TimeUS,Mode,ModeNum,Rsn"),
    "ARM": ("QBIBB", "TimeUS,ArmState,ArmChecks,Forced,Method"),
    "EV": ("QB", "TimeUS,Id"),
    "ERR": ("QBB", "TimeUS,Subsys,ECode"),
    "MSG": ("QZ", "TimeUS,Message"),
}


class DataFlashWriter:
    def __init__(self) -> None:
        self._types: dict[str, tuple[int, str, list[str]]] = {}
        self._records: list[tuple[int, bytes]] = []
        self._fmts: list[bytes] = []

    def _declare(self, name: str) -> tuple[int, str, list[str]]:
        if name not in self._types:
            fmt, cols = FORMATS[name]
            log_name = name.removesuffix("_OLD")
            type_id = len(self._types) + 1
            size = 3 + struct.calcsize("<" + "".join(_CODES[c][0] for c in fmt))
            self._fmts.append(
                HEAD
                + struct.pack(
                    "<BBB4s16s64s",
                    FMT_ID,
                    type_id,
                    size,
                    log_name.encode(),
                    fmt.encode(),
                    cols.encode(),
                )
            )
            self._types[name] = (type_id, fmt, cols.split(","))
        return self._types[name]

    def add(self, name: str, t: float, **values: Any) -> None:
        """Append one record at ``t`` seconds; missing fields are 0."""
        type_id, fmt, cols = self._declare(name)
        time_us = round(t * 1e6)
        packed = []
        for code, col in zip(fmt, cols, strict=True):
            st, scale = _CODES[code]
            v = time_us if col == "TimeUS" else values.get(col, 0)
            if st.endswith("s"):
                v = str(v).encode()
            elif scale is not None:
                v = round(v / scale)
            elif st in "bBhHiIqQ":
                v = int(v)
            packed.append(v)
        body = struct.pack("<" + "".join(_CODES[c][0] for c in fmt), *packed)
        self._records.append((time_us, HEAD + bytes([type_id]) + body))

    def write(self, path: Path) -> Path:
        records = [r for _, r in sorted(self._records, key=lambda r: r[0])]
        path.write_bytes(b"".join(self._fmts) + b"".join(records))
        return path
