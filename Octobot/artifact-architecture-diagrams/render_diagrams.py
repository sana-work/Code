from __future__ import annotations

from pathlib import Path
from typing import Iterable

from PIL import Image, ImageDraw, ImageFont


OUT = Path(__file__).resolve().parent
WIDTH = 1800
HEIGHT = 1050

COLORS = {
    "bg": "#F7F8FA",
    "ink": "#17212B",
    "muted": "#52606D",
    "line": "#64748B",
    "navy": "#173B57",
    "blue": "#DCEEFF",
    "blue_border": "#2B6F9C",
    "green": "#E0F3E8",
    "green_border": "#2D7A4B",
    "gold": "#FFF0C2",
    "gold_border": "#A56A00",
    "coral": "#FCE3DF",
    "coral_border": "#B9493A",
    "gray": "#E9EDF1",
    "gray_border": "#64748B",
    "white": "#FFFFFF",
    "red": "#B42318",
}

REGULAR = "/System/Library/Fonts/Supplemental/Arial.ttf"
BOLD = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(BOLD if bold else REGULAR, size)


F_TITLE = font(42, True)
F_SUBTITLE = font(22)
F_BOX_TITLE = font(24, True)
F_BODY = font(20)
F_SMALL = font(17)
F_LABEL = font(18, True)
F_STEP = font(19, True)


def text_width(draw: ImageDraw.ImageDraw, value: str, text_font: ImageFont.FreeTypeFont) -> int:
    box = draw.textbbox((0, 0), value, font=text_font)
    return box[2] - box[0]


def wrap(draw: ImageDraw.ImageDraw, value: str, text_font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    lines: list[str] = []
    for paragraph in value.split("\n"):
        if not paragraph:
            lines.append("")
            continue
        words = paragraph.split()
        current = words[0]
        for word in words[1:]:
            candidate = f"{current} {word}"
            if text_width(draw, candidate, text_font) <= max_width:
                current = candidate
            else:
                lines.append(current)
                current = word
        lines.append(current)
    return lines


def draw_wrapped(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    value: str,
    text_font: ImageFont.FreeTypeFont,
    fill: str,
    max_width: int,
    spacing: int = 7,
    anchor: str | None = None,
) -> int:
    lines = wrap(draw, value, text_font, max_width)
    line_height = text_font.size + spacing
    x, y = xy
    for line in lines:
        draw.text((x, y), line, font=text_font, fill=fill, anchor=anchor)
        y += line_height
    return y


def new_canvas(title: str, subtitle: str) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGB", (WIDTH, HEIGHT), COLORS["bg"])
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, WIDTH, 122), fill=COLORS["navy"])
    draw.text((70, 30), title, font=F_TITLE, fill=COLORS["white"])
    draw.text((72, 82), subtitle, font=F_SUBTITLE, fill="#DCE7EF")
    return image, draw


def box(
    draw: ImageDraw.ImageDraw,
    bounds: tuple[int, int, int, int],
    title: str,
    body: str = "",
    fill: str = "#FFFFFF",
    border: str = "#64748B",
    title_color: str | None = None,
    radius: int = 12,
) -> None:
    x1, y1, x2, y2 = bounds
    draw.rounded_rectangle(bounds, radius=radius, fill=fill, outline=border, width=3)
    title_fill = title_color or COLORS["ink"]
    draw.text((x1 + 24, y1 + 20), title, font=F_BOX_TITLE, fill=title_fill)
    if body:
        draw_wrapped(
            draw,
            (x1 + 24, y1 + 60),
            body,
            F_BODY,
            COLORS["muted"],
            x2 - x1 - 48,
            spacing=6,
        )


def pill(
    draw: ImageDraw.ImageDraw,
    center: tuple[int, int],
    value: str,
    fill: str,
    text_fill: str = "#FFFFFF",
) -> None:
    width = text_width(draw, value, F_LABEL) + 34
    height = 42
    x, y = center
    draw.rounded_rectangle(
        (x - width // 2, y - height // 2, x + width // 2, y + height // 2),
        radius=20,
        fill=fill,
    )
    draw.text((x, y), value, font=F_LABEL, fill=text_fill, anchor="mm")


def arrow(
    draw: ImageDraw.ImageDraw,
    start: tuple[int, int],
    end: tuple[int, int],
    label: str = "",
    color: str = "#64748B",
    width: int = 4,
    label_offset: tuple[int, int] = (0, -28),
) -> None:
    draw.line((start, end), fill=color, width=width)
    x1, y1 = start
    x2, y2 = end
    dx, dy = x2 - x1, y2 - y1
    length = max((dx * dx + dy * dy) ** 0.5, 1)
    ux, uy = dx / length, dy / length
    px, py = -uy, ux
    size = 15
    p1 = (x2, y2)
    p2 = (x2 - ux * size + px * size * 0.55, y2 - uy * size + py * size * 0.55)
    p3 = (x2 - ux * size - px * size * 0.55, y2 - uy * size - py * size * 0.55)
    draw.polygon((p1, p2, p3), fill=color)
    if label:
        mx = (x1 + x2) // 2 + label_offset[0]
        my = (y1 + y2) // 2 + label_offset[1]
        label_lines = wrap(draw, label, F_SMALL, 250)
        label_height = len(label_lines) * 23 + 12
        label_width = min(270, max(text_width(draw, line, F_SMALL) for line in label_lines) + 20)
        draw.rounded_rectangle(
            (mx - label_width // 2, my - 7, mx + label_width // 2, my + label_height),
            radius=7,
            fill=COLORS["bg"],
        )
        y = my
        for line in label_lines:
            draw.text((mx, y), line, font=F_SMALL, fill=COLORS["muted"], anchor="ma")
            y += 23


def orthogonal_arrow(
    draw: ImageDraw.ImageDraw,
    points: Iterable[tuple[int, int]],
    label: str = "",
    color: str = "#64748B",
    label_xy: tuple[int, int] | None = None,
) -> None:
    pts = list(points)
    for a, b in zip(pts, pts[1:]):
        draw.line((a, b), fill=color, width=4)
    arrow(draw, pts[-2], pts[-1], color=color, width=4)
    if label and label_xy:
        x, y = label_xy
        draw.text((x, y), label, font=F_SMALL, fill=COLORS["muted"], anchor="mm")


def save(image: Image.Image, name: str) -> None:
    image.save(OUT / name, format="PNG", optimize=True, dpi=(144, 144))


def current_problem() -> None:
    image, draw = new_canvas(
        "Current Problem",
        "Large deterministic tool results are routed through the model instead of preserved exactly.",
    )

    box(draw, (70, 210, 360, 390), "Tool result", "500-row table, multiple tables, or a long report", COLORS["blue"], COLORS["blue_border"])
    box(draw, (500, 210, 790, 390), "Executor / ADK", "Raw tool response is passed into model-visible function history", COLORS["gray"], COLORS["gray_border"])
    box(draw, (930, 210, 1220, 390), "LLM", "Reads, summarizes, and may retype deterministic content", COLORS["gold"], COLORS["gold_border"])
    box(draw, (1360, 210, 1650, 390), "Final response", "Model-authored copy becomes the client-visible source of truth", COLORS["coral"], COLORS["coral_border"])

    arrow(draw, (360, 300), (500, 300), "raw payload", label_offset=(0, -130))
    arrow(draw, (790, 300), (930, 300), "full payload consumes tokens", label_offset=(0, -130))
    arrow(draw, (1220, 300), (1360, 300), "recreated content", label_offset=(0, -130))

    draw.text((70, 475), "Why this fails", font=font(30, True), fill=COLORS["ink"])
    box(draw, (70, 535, 520, 760), "High token cost", "The model must ingest content that does not require reasoning or transformation.", COLORS["white"], COLORS["coral_border"])
    box(draw, (675, 535, 1125, 760), "Data and format drift", "Rows, columns, ordering, Markdown, or JSON can be dropped, changed, or corrupted.", COLORS["white"], COLORS["coral_border"])
    box(draw, (1280, 535, 1730, 760), "Follow-up gap", "A later request such as 'tell me about row 2' has no durable, scoped source to query.", COLORS["white"], COLORS["coral_border"])

    draw.rounded_rectangle((70, 835, 1730, 960), radius=12, fill="#FFF5F4", outline=COLORS["coral_border"], width=3)
    draw.text((100, 865), "Core issue", font=F_BOX_TITLE, fill=COLORS["red"])
    draw_wrapped(
        draw,
        (300, 858),
        "Exact presentation data and compact reasoning data are treated as one payload. The model becomes an unreliable formatting and storage layer.",
        F_BODY,
        COLORS["ink"],
        1370,
    )
    save(image, "01-current-problem.png")


def proposed_architecture() -> None:
    image, draw = new_canvas(
        "Proposed Architecture",
        "Separate compact reasoning context from durable deterministic artifacts, then materialize only at delivery.",
    )

    box(draw, (60, 180, 330, 330), "Tool call", "MCP, OpenAPI, or built-in", COLORS["blue"], COLORS["blue_border"])
    box(draw, (430, 180, 760, 330), "Artifact capture", "Verified ADK after_tool_callback; skip error payloads", COLORS["green"], COLORS["green_border"])
    box(draw, (860, 180, 1170, 330), "Deterministic split", "Configured scalar facts vs. large presentation content", COLORS["gold"], COLORS["gold_border"])

    arrow(draw, (330, 255), (430, 255))
    arrow(draw, (760, 255), (860, 255))

    box(draw, (690, 450, 990, 620), "llm_context", "Exact bounded facts needed now: pay_date, status, counts", COLORS["blue"], COLORS["blue_border"])
    box(draw, (1180, 450, 1510, 620), "ArtifactPGStore", "Canonical table/text, stable row IDs, checksum, ownership, TTL", COLORS["green"], COLORS["green_border"])
    orthogonal_arrow(draw, [(940, 330), (940, 390), (840, 390), (840, 450)], "small facts", COLORS["blue_border"], (815, 382))
    orthogonal_arrow(draw, [(1090, 330), (1090, 390), (1345, 390), (1345, 450)], "large content", COLORS["green_border"], (1315, 382))

    box(draw, (150, 690, 490, 860), "ADK model + history", "Sees only llm_context and artifact_refs. Raw artifact bytes never enter history.", COLORS["gray"], COLORS["gray_border"])
    box(draw, (665, 690, 1005, 860), "Compact response", "Narrative plus exact placeholder supplied by the capture result", COLORS["gold"], COLORS["gold_border"])
    box(draw, (1180, 690, 1530, 860), "Orchestrator boundary", "After all synthesis, resolve authorized refs and render once", COLORS["green"], COLORS["green_border"])
    box(draw, (1580, 690, 1745, 860), "Client", "Exact final result", COLORS["blue"], COLORS["blue_border"])

    orthogonal_arrow(draw, [(840, 620), (840, 650), (320, 650), (320, 690)], color=COLORS["blue_border"])
    orthogonal_arrow(draw, [(320, 860), (320, 910), (835, 910), (835, 860)], color=COLORS["gray_border"])
    arrow(draw, (1005, 775), (1180, 775), "compact refs only")
    orthogonal_arrow(draw, [(1345, 620), (1345, 690)], "authorized fetch", COLORS["green_border"], (1450, 652))
    arrow(draw, (1530, 775), (1580, 775))

    pill(draw, (345, 955), "INTERNAL: compact", COLORS["gray_border"])
    pill(draw, (1360, 955), "EXTERNAL: materialized", COLORS["green_border"])
    save(image, "02-proposed-architecture.png")


def phase_one_flow() -> None:
    image, draw = new_canvas(
        "Phase 1 End-to-End Flow",
        "Executor captures and stores; Orchestrator materializes only after final response synthesis.",
    )

    draw.rounded_rectangle((50, 165, 850, 970), radius=12, fill="#F1F7FB", outline=COLORS["blue_border"], width=3)
    draw.rounded_rectangle((950, 165, 1750, 970), radius=12, fill="#F2F9F4", outline=COLORS["green_border"], width=3)
    draw.text((85, 190), "EXECUTOR", font=font(28, True), fill=COLORS["blue_border"])
    draw.text((985, 190), "ORCHESTRATOR", font=font(28, True), fill=COLORS["green_border"])

    box(draw, (100, 270, 470, 400), "1. Tool returns", "Successful result may contain scalar facts and large content", COLORS["white"], COLORS["blue_border"])
    box(draw, (100, 470, 470, 625), "2. Capture callback", "Skip isError results; classify deterministically; fail closed on unsafe storage failure", COLORS["white"], COLORS["blue_border"])
    box(draw, (100, 710, 470, 865), "3. Compact step result", "Return llm_context, artifact_refs, and placeholders; persist compact ADK history", COLORS["white"], COLORS["blue_border"])
    box(draw, (560, 470, 800, 625), "Artifact store", "Durable tenant/session data", COLORS["green"], COLORS["green_border"])

    arrow(draw, (285, 400), (285, 470))
    arrow(draw, (470, 548), (560, 548), "atomic write")
    arrow(draw, (285, 625), (285, 710))

    box(draw, (1000, 270, 1370, 425), "4. prepare_response", "Only compact facts and refs enter output-generator synthesis", COLORS["white"], COLORS["green_border"])
    box(draw, (1000, 515, 1370, 670), "5. build final response", "All synthesis completes while content remains compact", COLORS["white"], COLORS["green_border"])
    box(draw, (1000, 760, 1370, 895), "6. Materialize once", "Resolve authorized refs, verify checksum, render exact content", COLORS["white"], COLORS["green_border"])
    box(draw, (1480, 760, 1700, 895), "7. Deliver", "HTTP or terminal SSE response", COLORS["blue"], COLORS["blue_border"])

    orthogonal_arrow(draw, [(470, 787), (900, 787), (900, 347), (1000, 347)], "compact cross-repo payload", COLORS["line"], (755, 745))
    arrow(draw, (1185, 425), (1185, 515))
    arrow(draw, (1185, 670), (1185, 760))
    orthogonal_arrow(draw, [(680, 625), (680, 920), (1185, 920), (1185, 895)], "authorized artifact read", COLORS["green_border"], (900, 948))
    arrow(draw, (1370, 827), (1480, 827))

    pill(draw, (530, 935), "Feature flag OFF by default", COLORS["navy"])
    save(image, "03-phase-1-end-to-end.png")


def follow_up_flow() -> None:
    image, draw = new_canvas(
        "Later Follow-Up: Query Only What Is Needed",
        "A narrow authorized query answers row-level questions without reloading the complete artifact.",
    )

    box(draw, (70, 200, 390, 350), "User", "Tell me more about row 2", COLORS["blue"], COLORS["blue_border"])
    box(draw, (500, 200, 820, 350), "Agent", "Reads compact session state and selects the prior artifact", COLORS["gray"], COLORS["gray_border"])
    box(draw, (930, 200, 1260, 350), "query_artifact", "artifact_id + row_number=2 + requested columns", COLORS["gold"], COLORS["gold_border"])
    box(draw, (1370, 200, 1720, 350), "ArtifactPGStore", "Tenant, use case, session, expiry, and checksum enforced", COLORS["green"], COLORS["green_border"])

    arrow(draw, (390, 275), (500, 275))
    arrow(draw, (820, 275), (930, 275), "bounded query", label_offset=(0, -105))
    arrow(draw, (1260, 275), (1370, 275), "authorize + read", label_offset=(0, -105))

    box(draw, (1370, 510, 1720, 665), "Stable row lookup", "'Row 2' maps to frozen row_ids[1], never a live database offset", COLORS["green"], COLORS["green_border"])
    box(draw, (930, 510, 1260, 665), "Narrow result", "Only the selected row and allowed columns are returned", COLORS["gold"], COLORS["gold_border"])
    box(draw, (500, 510, 820, 665), "Agent reasoning", "Model sees the narrow row, not the full table", COLORS["gray"], COLORS["gray_border"])
    box(draw, (70, 510, 390, 665), "Answer", "Explain row 2 using exact retrieved values", COLORS["blue"], COLORS["blue_border"])

    arrow(draw, (1545, 350), (1545, 510))
    arrow(draw, (1370, 588), (1260, 588), "single row", label_offset=(0, -105))
    arrow(draw, (930, 588), (820, 588))
    arrow(draw, (500, 588), (390, 588))

    draw.text((70, 760), "Guardrails", font=font(30, True), fill=COLORS["ink"])
    box(draw, (70, 815, 545, 955), "Ambiguity", "If two tables were displayed, ask which table instead of guessing.", COLORS["white"], COLORS["coral_border"])
    box(draw, (665, 815, 1140, 955), "Non-disclosure", "Missing and unauthorized IDs return the same generic not-found result.", COLORS["white"], COLORS["coral_border"])
    box(draw, (1260, 815, 1735, 955), "Hard limits", "Bound rows, columns, bytes, filters, aggregate work, and execution time.", COLORS["white"], COLORS["coral_border"])
    save(image, "04-follow-up-query.png")


def implementation_phases() -> None:
    image, draw = new_canvas(
        "Current Implementation Plan",
        "Deliver in gated phases; verify each phase before expanding execution modes or follow-up capability.",
    )

    y = 260
    line_y = 520
    draw.line((120, line_y, 1680, line_y), fill=COLORS["line"], width=7)

    phases = [
        (200, "Phase 0", "VERIFIED", "Boundary, ADK callbacks, plugin order, DB pattern, idempotency", COLORS["green"], COLORS["green_border"]),
        (550, "Phase 1", "NEXT", "Sync/Stream capture in Executor; final materialization in Orchestrator", COLORS["blue"], COLORS["blue_border"]),
        (900, "Phase 2", "LATER", "query_artifact, stable rows, projections, ambiguity, aggregates", COLORS["gold"], COLORS["gold_border"]),
        (1250, "Phase 3", "LATER", "Async, Hybrid, Resume, retry, cleanup, process restart", COLORS["gray"], COLORS["gray_border"]),
        (1600, "Phase 4", "LATER", "Full prompt-isolation audit and all synthesis paths", COLORS["coral"], COLORS["coral_border"]),
    ]

    for x, phase, status, description, fill, border in phases:
        draw.ellipse((x - 20, line_y - 20, x + 20, line_y + 20), fill=border)
        bounds = (x - 145, y, x + 145, y + 190)
        box(draw, bounds, phase, description, fill, border)
        pill(draw, (x, y + 220), status, border)

    draw.text((80, 700), "Approved Phase 1 decisions", font=font(30, True), fill=COLORS["ink"])
    box(draw, (80, 765, 570, 940), "Cross-repository boundary", "Executor stores compact artifacts. Orchestrator materializes only after final synthesis.", COLORS["white"], COLORS["green_border"])
    box(draw, (655, 765, 1145, 940), "Dedicated opt-in", "enable_artifact_capture is independent of audit logging and defaults to false.", COLORS["white"], COLORS["blue_border"])
    box(draw, (1230, 765, 1720, 940), "Fail closed", "Storage failure never sends protected raw content into model context.", COLORS["white"], COLORS["coral_border"])
    save(image, "05-implementation-phases.png")


def main() -> None:
    current_problem()
    proposed_architecture()
    phase_one_flow()
    follow_up_flow()
    implementation_phases()


if __name__ == "__main__":
    main()
