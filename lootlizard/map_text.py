"""Optional, offline place-label evidence; never a map registration transform.

Windows OCR currently works on the development host through Windows PowerShell
5.1, using only installed language packs. Microsoft documents desktop OCR with
package identity/MSIX, so this unpackaged bridge is best-effort, optional and
fail-soft. No executable, model or language pack is downloaded by this module.

Primary documentation:
https://learn.microsoft.com/en-us/uwp/api/windows.media.ocr
https://learn.microsoft.com/en-us/uwp/api/windows.media.ocr.ocrengine.maximagedimension
https://learn.microsoft.com/en-us/uwp/api/windows.media.ocr.ocrengine.trycreatefromlanguage

The small English-label vocabulary below was checked against local map views.
It is a closed set of textual hints, not a complete/current city catalog.
Generic/shared words (School, Prison, Terminal, Palace, Camp, etc.) are excluded.
Two distinct, spatially separated label matches are required. OCR can still
misread text or find text outside a game map: a suggestion must never revive a
failed transform, establish map visibility, or place POIs.
"""

from dataclasses import dataclass
import base64
from io import BytesIO
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time
import unicodedata
from typing import Iterable

import numpy as np
from PIL import Image


LABELS = {
    "erangel": ("Georgopol", "Rozhok", "Yasnaya Polyana", "Pochinki", "Gatka", "Mylta",
                "Novorepnoye", "Lipovka", "Primorsk", "Severny", "Kameshki", "Zharki",
                "Sosnovka Military Base", "Stalber"),
    "taego": ("Ho San", "Buk San Sa", "Kang Neung"),
}
_MAX_OCR_SIDE = 3000
_MAX_PIXELS = 40_000_000


@dataclass(frozen=True)
class LabelMatch:
    label: str
    observed: str
    bounds: tuple[float, float, float, float]  # full image x, y, width, height
    edits: int


@dataclass(frozen=True)
class MapTextEvidence:
    map_id: str | None
    matched_labels: tuple[str, ...]
    reason: str
    matches: tuple[LabelMatch, ...] = ()
    available: bool = False
    backend: str = "windows-ocr-optional"


_BRIDGE = r'''
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Console]::InputEncoding = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
try {
    Add-Type -AssemblyName System.Runtime.WindowsRuntime
    $null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType=WindowsRuntime]
    $null = [Windows.Globalization.Language, Windows.Foundation, ContentType=WindowsRuntime]
    $null = [Windows.Storage.Streams.InMemoryRandomAccessStream, Windows.Storage.Streams, ContentType=WindowsRuntime]
    $null = [Windows.Storage.Streams.DataWriter, Windows.Storage.Streams, ContentType=WindowsRuntime]
    $null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics.Imaging, ContentType=WindowsRuntime]
    $null = [Windows.Graphics.Imaging.SoftwareBitmap, Windows.Graphics.Imaging, ContentType=WindowsRuntime]
    $asTask = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
        $_.Name -eq 'AsTask' -and $_.IsGenericMethod -and $_.GetParameters().Count -eq 1 -and
        $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
    } | Select-Object -First 1
    function Await($Operation, $ResultType) {
        $task = $asTask.MakeGenericMethod($ResultType).Invoke($null, @($Operation))
        $task.GetAwaiter().GetResult()
    }
    $request = [Console]::In.ReadToEnd() | ConvertFrom-Json
    $languages = @([Windows.Media.Ocr.OcrEngine]::AvailableRecognizerLanguages | ForEach-Object { $_.LanguageTag })
    $limit = [Windows.Media.Ocr.OcrEngine]::MaxImageDimension
    if ($request.mode -eq 'capabilities') {
        @{ok=$true; languages=$languages; max_image_dimension=$limit} | ConvertTo-Json -Compress
        exit 0
    }
    $language = New-Object Windows.Globalization.Language('en-US')
    $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage($language)
    if ($null -eq $engine) { throw 'English OCR language is not installed' }
    $outputs = @()
    foreach ($frame in $request.frames) {
        $stream = New-Object Windows.Storage.Streams.InMemoryRandomAccessStream
        $writer = New-Object Windows.Storage.Streams.DataWriter($stream)
        $writer.WriteBytes([Convert]::FromBase64String($frame.png_base64))
        $null = Await ($writer.StoreAsync()) ([uint32])
        $null = $writer.DetachStream()
        $writer.Dispose()
        $stream.Seek(0)
        $decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
        if ($decoder.PixelWidth -gt $limit -or $decoder.PixelHeight -gt $limit) { throw 'Image exceeds Windows OCR MaxImageDimension' }
        $bitmap = Await ($decoder.GetSoftwareBitmapAsync([Windows.Graphics.Imaging.BitmapPixelFormat]::Bgra8,
                        [Windows.Graphics.Imaging.BitmapAlphaMode]::Premultiplied)) ([Windows.Graphics.Imaging.SoftwareBitmap])
        $result = Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
        $lines = @($result.Lines | ForEach-Object {
            @{text=$_.Text; words=@($_.Words | ForEach-Object {
                @{text=$_.Text; bounds=@($_.BoundingRect.X, $_.BoundingRect.Y, $_.BoundingRect.Width, $_.BoundingRect.Height)}
            })}
        })
        $outputs += @{lines=$lines}
        $bitmap.Dispose()
        $stream.Dispose()
    }
    @{ok=$true; frames=$outputs; language=$engine.RecognizerLanguage.LanguageTag;
      languages=$languages; max_image_dimension=$limit} | ConvertTo-Json -Depth 8 -Compress
} catch {
    @{ok=$false; error=$_.Exception.Message} | ConvertTo-Json -Compress
}
'''


def _powershell() -> Path | None:
    if sys.platform != "win32":
        return None
    path = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    return path if path.is_file() else None


def _run_bridge(request: dict, timeout: float) -> dict:
    executable = _powershell()
    if executable is None:
        return {"ok": False, "error": "Optional Windows OCR is unavailable on this platform"}
    command = base64.b64encode(_BRIDGE.encode("utf-16le")).decode("ascii")
    completed = subprocess.run(
        [str(executable), "-NoProfile", "-NonInteractive", "-EncodedCommand", command],
        input=json.dumps(request), capture_output=True, text=True, encoding="utf-8",
        timeout=max(.05, timeout), creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if completed.returncode != 0:
        return {"ok": False, "error": "The optional Windows OCR process failed"}
    if len(completed.stdout) > 2_000_000:
        return {"ok": False, "error": "Windows OCR returned too much text"}
    response = json.loads(completed.stdout)
    if not isinstance(response, dict):
        raise ValueError("Invalid Windows OCR response")
    return response


def ocr_capabilities(*, timeout: float = 3.) -> dict:
    """Read installed OCR packs; success here does not guarantee deployment support."""
    try:
        return _run_bridge({"mode": "capabilities"}, min(3., max(.05, float(timeout))))
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        return {"ok": False, "error": str(error)}


def _normalized(value: str) -> str:
    return "".join(character.lower() for character in unicodedata.normalize("NFKD", value)
                   if character.isascii() and character.isalpha())


def _distance(left: str, right: str) -> int:
    previous = list(range(len(right)+1))
    for index, a in enumerate(left, 1):
        current = [index]
        for j, b in enumerate(right, 1):
            current.append(min(current[-1]+1, previous[j]+1, previous[j-1]+(a != b)))
        previous = current
    return previous[-1]


def _interpret(response: dict, allowed: tuple[str, ...], image_size, factors, deadline=None) -> MapTextEvidence:
    if response.get("ok") is not True:
        return MapTextEvidence(None, (), "Optional OCR unavailable: " + str(response.get("error", "unknown error")))
    width, height = image_size
    candidates = {map_id: {} for map_id in allowed if map_id in LABELS}
    frames = response.get("frames", [])
    if not isinstance(frames, list) or len(frames) > 2:
        raise ValueError("Invalid OCR frames")
    total_words = 0
    for frame in frames:
        if not isinstance(frame, dict) or not isinstance(frame.get("lines"), list) or len(frame["lines"]) > 1000:
            raise ValueError("Invalid OCR lines")
        for line in frame["lines"]:
            if not isinstance(line, dict) or not isinstance(line.get("words"), list):
                raise ValueError("Invalid OCR words")
            words = line.get("words", [])
            total_words += len(words)
            if total_words > 2000 or not all(isinstance(word, dict) for word in words):
                raise ValueError("Too many or invalid OCR words")
            for first in range(len(words)):
                if deadline is not None and time.monotonic() >= deadline:
                    return MapTextEvidence(None, (), "Optional OCR timed out")
                for last in range(first+1, min(first+4, len(words))+1):
                    phrase = words[first:last]
                    text = " ".join(str(word.get("text", "")) for word in phrase)
                    value = _normalized(text)
                    if not 5 <= len(value) <= 35:
                        continue
                    boxes = [word.get("bounds") for word in phrase]
                    if not all(isinstance(box, list) and len(box) == 4 and all(
                            isinstance(n, (int, float)) and math.isfinite(n) for n in box) for box in boxes):
                        continue
                    if any(box[2] <= 0 or box[3] <= 0 for box in boxes):
                        continue
                    if any(abs((a[1]+a[3]/2)-(b[1]+b[3]/2)) > max(a[3], b[3])*.6
                           or not -max(a[3], b[3])*.5 <= b[0]-(a[0]+a[2]) <= max(a[3], b[3])*1.6
                           for a, b in zip(boxes, boxes[1:])):
                        continue
                    left = min(box[0] for box in boxes)/factors[0]
                    top = min(box[1] for box in boxes)/factors[1]
                    right = max(box[0]+box[2] for box in boxes)/factors[0]
                    bottom = max(box[1]+box[3] for box in boxes)/factors[1]
                    if not (0 <= left < right <= width and 0 <= top < bottom <= height):
                        continue
                    # Avoid common perimeter grid/HUD text; this is not a HUD detector.
                    if not (.04*width < (left+right)/2 < .96*width
                            and .04*height < (top+bottom)/2 < .94*height):
                        continue
                    for map_id, names in ((key, LABELS[key]) for key in candidates):
                        for label in names:
                            expected = _normalized(label)
                            maximum = 0 if len(expected) < 8 else (1 if len(expected) < 9 else 2)
                            if abs(len(value)-len(expected)) > maximum:
                                continue
                            edits = _distance(value, expected)
                            if edits > maximum:
                                continue
                            match = LabelMatch(label, text, (left, top, right-left, bottom-top), edits)
                            old = candidates[map_id].get(label)
                            if old is None or edits < old.edits:
                                candidates[map_id][label] = match
    qualified = []
    for map_id, labels in candidates.items():
        matches = tuple(labels.values())
        # Different OCR variants of one location are still just one label.
        separated = any(math.hypot(a.bounds[0]-b.bounds[0], a.bounds[1]-b.bounds[1])
                        >= max(40., min(width, height)*.08)
                        for i, a in enumerate(matches) for b in matches[i+1:])
        if len(matches) >= 2 and separated:
            qualified.append((map_id, matches))
    all_matches = tuple(match for labels in candidates.values() for match in labels.values())
    if len(qualified) == 1 and any(labels for map_id, labels in candidates.items() if map_id != qualified[0][0]):
        return MapTextEvidence(None, tuple(match.label for match in all_matches),
                               "Conflicting place-label evidence", all_matches, True)
    if len(qualified) != 1:
        reason = ("Ambiguous place-label evidence" if len(qualified) > 1
                  else "Insufficient distinct, separated place labels")
        return MapTextEvidence(None, tuple(match.label for match in all_matches), reason, all_matches, True)
    map_id, matches = qualified[0]
    return MapTextEvidence(map_id, tuple(match.label for match in matches),
                           "Place text suggests a map only; zoom out for verified point placement", matches, True)


def identify_map_text(image: Image.Image, allowed_map_ids: Iterable[str], *, timeout: float = 8.) -> MapTextEvidence:
    """Best-effort textual hint from pixels, bounded to at most eight seconds.

    PNGs travel through a hidden process's stdin and in-memory WinRT streams;
    no screenshot or recognized text is saved, uploaded or added to app state.
    The result has no map transform, POI coordinates or player identity.
    """
    started = time.monotonic()
    try:
        if not isinstance(image, Image.Image) or min(image.size) < 1 or image.width*image.height > _MAX_PIXELS:
            raise ValueError("A PIL image of at most 40 million pixels is required")
        if isinstance(allowed_map_ids, str):
            raise ValueError("Provide a collection of map ids")
        allowed = tuple(dict.fromkeys(allowed_map_ids))
        if not all(isinstance(value, str) for value in allowed):
            raise ValueError("Map ids must be strings")
        if not set(allowed).intersection(LABELS):
            return MapTextEvidence(None, (), "No place-label vocabulary for the allowed map ids")
        requested_timeout = float(timeout)
        if not math.isfinite(requested_timeout):
            raise ValueError("OCR timeout must be finite")
        budget = min(8., max(.05, requested_timeout))
        factor = min(1., _MAX_OCR_SIDE/max(image.size))
        size = (max(1, round(image.width*factor)), max(1, round(image.height*factor)))
        if image.mode == "RGBA":
            rgb = Image.new("RGB", image.size)
            rgb.paste(image, mask=image.getchannel("A"))
        else:
            rgb = image.convert("RGB")
        rgb = rgb.resize(size, Image.Resampling.LANCZOS)
        array = np.asarray(rgb).astype(np.int16)
        white = (np.max(array, 2)-np.min(array, 2) < 35) & (np.min(array, 2) > 135)
        variants = (rgb, Image.fromarray((~white).astype(np.uint8)*255).convert("RGB"))
        frames = []
        for variant in variants:
            buffer = BytesIO()
            variant.save(buffer, format="PNG", compress_level=1)
            frames.append({"png_base64": base64.b64encode(buffer.getvalue()).decode("ascii")})
        remaining = budget-(time.monotonic()-started)-.05
        if remaining <= 0:
            return MapTextEvidence(None, (), "Optional OCR timed out")
        response = _run_bridge({"mode": "recognize", "frames": frames}, remaining)
        factors = (size[0]/image.width, size[1]/image.height)
        return _interpret(response, allowed, image.size, factors, started+budget)
    except subprocess.TimeoutExpired:
        return MapTextEvidence(None, (), "Optional OCR timed out")
    except (OSError, ValueError, TypeError, subprocess.SubprocessError) as error:
        return MapTextEvidence(None, (), "Optional OCR unavailable: " + str(error))
