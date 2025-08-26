# -*- coding: utf-8 -*-
"""
make_subs.py
Create SRT and VTT subtitles from a transcript (.docx or .txt) and an audio (.mp3).
Usage:
    python make_subs.py --audio "path/to/audio.mp3" --transcript "path/to/transcript.docx" --out "out_basename"
Notes:
- Duration read via mutagen (fallback to pydub). If both not available, provide --duration as seconds.
- Chunking is proportional to text length; tweak --target_chars/--max_chars/--min_dur/--max_dur as needed.
"""
import argparse, re, textwrap

def read_mp3_duration_seconds(path, fallback=None):
    length = None
    try:
        from mutagen.mp3 import MP3
        length = MP3(path).info.length
    except Exception:
        try:
            from pydub import AudioSegment
            length = len(AudioSegment.from_mp3(path)) / 1000.0
        except Exception:
            length = fallback
    return float(length) if length is not None else None

def extract_text(transcript_path):
    txt = None
    if transcript_path.lower().endswith(".docx"):
        try:
            import docx
            doc = docx.Document(transcript_path)
            paras = []
            for p in doc.paragraphs:
                if p.text and p.text.strip():
                    paras.append(p.text.strip())
            txt = "\n".join(paras).strip()
        except Exception:
            pass
    if txt is None:
        with open(transcript_path, "r", encoding="utf-8") as f:
            txt = f.read()
    return txt

def normalize_text(txt):
    txt = txt.replace("\r\n", "\n").replace("\r", "\n")
    txt = re.sub(r"[ \t]+", " ", txt)
    txt = re.sub(r"\n{2,}", "\n", txt)
    return txt.strip()

def split_sentences(txt):
    parts = re.split(r"([。！？!?…]+|\n)", txt)
    sentences, cur = [], ""
    for part in parts:
        if part is None or part == "":
            continue
        if re.match(r"^[。！？!?…]+$|^\n$", part):
            cur += part.replace("\n","")
            if cur.strip():
                sentences.append(cur.strip())
            cur = ""
        else:
            cur += part
    if cur.strip():
        sentences.append(cur.strip())
    merged = []
    for s in sentences:
        if merged and len(s) < 6:
            merged[-1] += s if s.endswith(("。","！","？","…")) else s + "。"
        else:
            merged.append(s)
    return merged

def group_into_chunks(sentences, target_chars=22, max_chars=42):
    chunks, current = [], ""
    for s in sentences:
        if len(current) + len(s) + (0 if current=="" else 1) <= max_chars:
            current = (current + " " + s).strip() if current else s
        else:
            if current:
                chunks.append(current)
            if len(s) > max_chars:
                start = 0
                while start < len(s):
                    end = min(start + target_chars, len(s))
                    chunks.append(s[start:end])
                    start = end
            else:
                current = s
    if current:
        chunks.append(current)
    return chunks

def seconds_to_timestamp(secs):
    if secs < 0: secs = 0
    h = int(secs // 3600); m = int((secs % 3600) // 60); s = int(secs % 60)
    ms = int(round((secs - int(secs)) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

def seconds_to_vtt_timestamp(secs):
    if secs < 0: secs = 0
    h = int(secs // 3600); m = int((secs % 3600) // 60); s = int(secs % 60)
    ms = int(round((secs - int(secs)) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"

def build_subtitles(text, duration_sec, target_chars=22, max_chars=42, min_dur=1.8, max_dur=6.0, offset=0.0):
    text = normalize_text(text)
    sentences = split_sentences(text)
    total_chars = max(sum(len(s) for s in sentences), 1)
    sec_per_char = duration_sec / total_chars
    chunks = group_into_chunks(sentences, target_chars=target_chars, max_chars=max_chars)

    times, cur_t = [], 0.0
    for chunk in chunks:
        dur = max(min_dur, min(max_dur, len(chunk) * sec_per_char))
        start, end = cur_t, cur_t + dur
        times.append((start, end)); cur_t = end

    if times:
        final_end = times[-1][1]
        if final_end != duration_sec and final_end > 0:
            ratio = duration_sec / final_end
            times = [(s*ratio, e*ratio) for (s,e) in times]

    srt_lines = []
    for idx, ((start, end), chunk) in enumerate(zip(times, chunks), 1):
        srt_lines.append(str(idx))
        srt_lines.append(f"{seconds_to_timestamp(start)} --> {seconds_to_timestamp(end)}")
        wrapped = textwrap.wrap(chunk, width=24, replace_whitespace=False, drop_whitespace=False)
        srt_lines.extend(wrapped if wrapped else [chunk])
        srt_lines.append("")

    vtt_lines = ["WEBVTT", ""]
    for (start, end), chunk in zip(times, chunks):
        vtt_lines.append(f"{seconds_to_vtt_timestamp(start)} --> {seconds_to_vtt_timestamp(end)}")
        wrapped = textwrap.wrap(chunk, width=24, replace_whitespace=False, drop_whitespace=False)
        vtt_lines.extend(wrapped if wrapped else [chunk])
        vtt_lines.append("")

    return "\n".join(srt_lines).strip() + "\n", "\n".join(vtt_lines).strip() + "\n"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--audio", required=True)
    ap.add_argument("--transcript", required=True)
    ap.add_argument("--out", default="subs")
    ap.add_argument("--duration", type=float, default=None, help="Fallback duration seconds if audio read fails")
    ap.add_argument("--target_chars", type=int, default=22)
    ap.add_argument("--max_chars", type=int, default=42)
    ap.add_argument("--min_dur", type=float, default=1.8)
    ap.add_argument("--max_dur", type=float, default=6.0)
    ap.add_argument("--offset", type=float, default=0.0, help="Shift all subtitle timestamps by seconds (positive = delay)")
    args = ap.parse_args()

    dur = read_mp3_duration_seconds(args.audio, fallback=args.duration)
    if dur is None:
        raise SystemExit("Could not read audio duration. Install 'mutagen' or 'pydub', or pass --duration.")

    text = extract_text(args.transcript)
    srt, vtt = build_subtitles(text, dur, args.target_chars, args.max_chars, args.min_dur, args.max_dur, args.offset)
    if args.offset:
        # Quick shift for both formats
        import re
        def _parse(ts):
            h,m,rest = ts.split(":"); s,ms = rest.replace(",",".").split("."); return int(h)*3600+int(m)*60+int(s)+int(ms)/1000.0
        def _fmt_srt(t):
            h=int(t//3600); m=int((t%3600)//60); s=int(t%60); ms=int(round((t-int(t))*1000)); return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
        def _fmt_vtt(t):
            h=int(t//3600); m=int((t%3600)//60); s=int(t%60); ms=int(round((t-int(t))*1000)); return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"
        def _shift_block(txt, vtt=False):
            out=[]
            for line in txt.splitlines():
                if "-->" in line:
                    a,b = line.split("-->")
                    st=_parse(a.strip()); en=_parse(b.strip()); st+=args.offset; en+=args.offset
                    out.append((f"{_fmt_vtt(st)} --> {_fmt_vtt(en)}") if vtt else (f"{_fmt_srt(st)} --> {_fmt_srt(en)}"))
                else:
                    out.append(line)
            return "\n".join(out)+"\n"
        srt=_shift_block(srt, vtt=False)
        vtt=_shift_block(vtt, vtt=True)

    with open(args.out + ".srt", "w", encoding="utf-8") as f:
        f.write(srt)
    with open(args.out + ".vtt", "w", encoding="utf-8") as f:
        f.write(vtt)
    print(f"Wrote {args.out}.srt and {args.out}.vtt")

if __name__ == "__main__":
    main()
