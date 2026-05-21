#!/usr/bin/env python3
"""
SSH 명령 출력을 터미널 스타일 PNG 이미지로 렌더링.
사용법: python3 render_terminal.py --output out.png [--width 900] < text_input
     또는: python3 render_terminal.py --output out.png --text "출력 텍스트"
"""
import sys, re, argparse
from PIL import Image, ImageDraw, ImageFont

# ── 터미널 색상 팔레트 (Solarized Dark 계열) ──────────────────────────────
BG        = (30,  30,  30)   # 배경
FG        = (220, 220, 220)  # 기본 텍스트
ANSI_COLORS = {
    30: (30,  30,  30),   # black
    31: (205, 49,  49),   # red
    32: (13, 188, 121),   # green  ← 프롬프트 user@host
    33: (229, 229, 16),   # yellow
    34: (36, 114, 200),   # blue   ← 프롬프트 경로
    35: (188, 63, 188),   # magenta
    36: (17, 168, 205),   # cyan
    37: (229, 229, 229),  # white
    90: (102, 102, 102),  # bright black
    91: (241, 76,  76),   # bright red
    92: (35, 209, 139),   # bright green
    93: (245,245, 67),    # bright yellow
    94: (59, 142, 234),   # bright blue
    95: (214, 112, 214),  # bright magenta
    96: (41, 184, 219),   # bright cyan
    97: (229, 229, 229),  # bright white
}

import os
FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"

if not os.path.exists(FONT_PATH):
    # macOS fallback
    mac_font = "/System/Library/Fonts/Supplemental/Courier New.ttf"
    mac_bold = "/System/Library/Fonts/Supplemental/Courier New Bold.ttf"
    if os.path.exists(mac_font):
        FONT_PATH = mac_font
        FONT_BOLD = mac_bold

def parse_ansi(text):
    """ANSI 이스케이프 시퀀스를 파싱해 (text, fg_color, bold) 세그먼트 리스트 반환."""
    segments = []
    pattern = re.compile(r'\033\[([0-9;]*)m')
    cur_fg   = FG
    cur_bold = False
    pos = 0
    for m in pattern.finditer(text):
        # 이스케이프 앞의 일반 텍스트
        if m.start() > pos:
            segments.append((text[pos:m.start()], cur_fg, cur_bold))
        # 코드 처리
        codes = [int(c) if c else 0 for c in m.group(1).split(';')]
        for code in codes:
            if code == 0:
                cur_fg, cur_bold = FG, False
            elif code == 1:
                cur_bold = True
            elif code == 22:
                cur_bold = False
            elif code in ANSI_COLORS:
                cur_fg = ANSI_COLORS[code]
        pos = m.end()
    if pos < len(text):
        segments.append((text[pos:], cur_fg, cur_bold))
    return segments

def wrap_line(line, font, bold_font, max_w):
    """긴 줄을 max_w 픽셀에 맞게 분할 (세그먼트 보존)."""
    segs = parse_ansi(line)
    rows = []
    cur_row = []
    cur_w = 0
    for (txt, fg, bold) in segs:
        f = bold_font if bold else font
        for ch in txt:
            cw = f.getlength(ch)
            if cur_w + cw > max_w and cur_row:
                rows.append(cur_row)
                cur_row = []
                cur_w = 0
            cur_row.append((ch, fg, bold))
            cur_w += cw
    if cur_row:
        rows.append(cur_row)
    return rows if rows else [[]]

def render(lines, output_path, img_width=920, font_size=15,
           pad_x=20, pad_y=16, line_gap=4, title="Terminal"):
    font      = ImageFont.truetype(FONT_PATH, font_size)
    bold_font = ImageFont.truetype(FONT_BOLD, font_size)

    # ascent/descent로 실제 줄 높이 계산
    ascent, descent = font.getmetrics()
    line_h = ascent + descent + line_gap

    # 제목 바 높이
    title_h = 36

    # 모든 줄을 래핑
    content_w = img_width - pad_x * 2
    all_rows = []
    for line in lines:
        rows = wrap_line(line, font, bold_font, content_w)
        all_rows.extend(rows)

    img_height = title_h + pad_y + len(all_rows) * line_h + pad_y

    img  = Image.new("RGB", (img_width, img_height), BG)
    draw = ImageDraw.Draw(img)

    # ── 제목 바 ───────────────────────────────────────────────────────────
    draw.rectangle([0, 0, img_width, title_h], fill=(50, 50, 50))
    # 신호등 버튼
    for i, color in enumerate([(255,95,87), (255,189,46), (40,200,64)]):
        cx = 18 + i * 22
        draw.ellipse([cx-6, title_h//2-6, cx+6, title_h//2+6], fill=color)
    # 제목 텍스트
    title_font = ImageFont.truetype(FONT_PATH, 13)
    tw = title_font.getlength(title)
    draw.text(((img_width - tw) / 2, (title_h - font_size) / 2),
              title, font=title_font, fill=(180, 180, 180))

    # ── 본문 텍스트 ────────────────────────────────────────────────────────
    y = title_h + pad_y
    for row in all_rows:
        x = pad_x
        for (ch, fg, bold) in row:
            f = bold_font if bold else font
            draw.text((x, y), ch, font=f, fill=fg)
            x += f.getlength(ch)
        y += line_h

    img.save(output_path, "PNG")
    print(f"저장: {output_path}  ({img_width}×{img_height})")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output",    required=True)
    ap.add_argument("--text",      default=None,    help="캡처된 명령 출력 텍스트")
    ap.add_argument("--width",     type=int, default=920)
    ap.add_argument("--font-size", type=int, default=15)
    ap.add_argument("--title",     default=None,    help="창 제목 (기본: user@hostname: cwd)")
    # 프롬프트 구성 파라미터 — 지정하면 프롬프트 줄을 자동 생성
    ap.add_argument("--hostname",  default=None,    help="프롬프트에 표시할 호스트명 (예: matter)")
    ap.add_argument("--user",      default="ubuntu",help="프롬프트 사용자명")
    ap.add_argument("--cwd",       default="~",     help="프롬프트 작업 디렉토리")
    ap.add_argument("--cmd",       default=None,    help="프롬프트에 표시할 명령어")
    args = ap.parse_args()

    raw = args.text if args.text else sys.stdin.read()

    # --hostname + --cmd 가 모두 주어지면 프롬프트 줄을 자동으로 앞에 추가
    if args.hostname and args.cmd:
        prompt = (
            f"\033[32m{args.user}@{args.hostname}\033[0m"
            f":\033[34m{args.cwd}\033[0m"
            f"$ {args.cmd}"
        )
        raw = prompt + "\n" + raw

    # 창 제목 기본값
    title = args.title or f"{args.user}@{args.hostname or 'server'}: {args.cwd}"

    lines = raw.expandtabs(4).splitlines()
    render(lines, args.output, img_width=args.width,
           font_size=args.font_size, title=title)

if __name__ == "__main__":
    main()
