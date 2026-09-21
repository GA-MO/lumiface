"""One pool for every CPU-bound step of a session (video decode, the pipeline, the frame store), sized so
the ONNX sessions never oversubscribe the machine: each model runs `INFERENCE_THREADS` intra-op threads and
at most `MAX_CONCURRENT_ANALYSES` sessions are judged at once. Beyond that the pool queues, and the stream
handler refuses new sockets (`SERVER_BUSY`) once `MAX_OPEN_STREAMS` are open so the queue stays short."""
from __future__ import annotations

import asyncio
import contextvars
import functools
import os
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from typing import Callable, TypeVar

import onnxruntime as ort

from ..config import get_settings

T = TypeVar("T")


def session_options() -> ort.SessionOptions:
    so = ort.SessionOptions()
    so.intra_op_num_threads = max(get_settings().inference_threads, 1)
    so.inter_op_num_threads = 1
    return so


def analysis_slots() -> int:
    s = get_settings()
    if s.max_concurrent_analyses > 0:
        return s.max_concurrent_analyses
    return max(1, (os.cpu_count() or 1) // max(s.inference_threads, 1))


def open_stream_slots() -> int:
    s = get_settings()
    return s.max_open_streams if s.max_open_streams > 0 else 4 * analysis_slots()


@lru_cache
def pool() -> ThreadPoolExecutor:
    return ThreadPoolExecutor(analysis_slots(), thread_name_prefix="lumiface-analysis")


async def run(fn: Callable[..., T], *args) -> T:
    ctx = contextvars.copy_context()
    return await asyncio.get_running_loop().run_in_executor(pool(), functools.partial(ctx.run, fn, *args))
