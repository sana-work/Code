"""Render the single-agent architecture as PNG, SVG and vector PDF."""
from pathlib import Path
from xml.etree import ElementTree as ET
import json
import math

from PIL import Image, ImageDraw, ImageFont
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.colors import toColor


OUT = Path("/Users/sanaiqbal/Codes/Code/Octobot/architecture-single-agent-update")
OUT.mkdir(parents=True, exist_ok=True)
NAME = "Universal_Chat_Single_Agent_Architecture"
W, H = 3200, 1600
REG = "/System/Library/Fonts/Supplemental/Arial.ttf"
BOLD = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
pdfmetrics.registerFont(TTFont("DiagramArial", REG))
pdfmetrics.registerFont(TTFont("DiagramArialBold", BOLD))

INK = "#17212D"
MUTED = "#566270"
BLUE = "#246CEB"
TEAL = "#078563"
PURPLE = "#8055CC"
AMBER = "#C87C10"
GRAY = "#728093"
NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", NS)


class Diagram:
    def __init__(self):
        self.image = Image.new("RGB", (W, H), "white")
        self.draw = ImageDraw.Draw(self.image)
        self.svg = ET.Element(f"{{{NS}}}svg", {
            "width": str(W), "height": str(H), "viewBox": f"0 0 {W} {H}",
            "role": "img", "aria-labelledby": "diagramTitle diagramDescription",
        })
        ET.SubElement(self.svg, "title", {"id": "diagramTitle"}).text = (
            "Universal Chat / VEGA / Octobot: single-agent architecture"
        )
        ET.SubElement(self.svg, "desc", {"id": "diagramDescription"}).text = (
            "Operations user, Live VEGA Chat and Chat BFF connect to one Universal Chat agent. "
            "The agent calls one Asset Services tool and three Transaction Management tools "
            "through the MCP server. Authenticated custody access uses API Management. "
            "Governed model access uses R2D2 and Vertex AI. Response controls include one "
            "final JSON object, summary-first output, compact or full evidence, and zero-time date display."
        )
        ET.SubElement(self.svg, "rect", {"width": str(W), "height": str(H), "fill": "white"})
        self.pdf = canvas.Canvas(str(OUT / f"{NAME}.pdf"), pagesize=(W, H))
        self.pdf.setTitle("Universal Chat / VEGA / Octobot - Single-Agent Architecture")
        self.pdf.setAuthor("Universal Chat Architecture")
        self.text_bounds = []

    def rect(self, x, y, w, h, fill="white", stroke=GRAY, radius=12, width=3, dashed=False):
        attrs = {"x": str(x), "y": str(y), "width": str(w), "height": str(h),
                 "rx": str(radius), "fill": fill, "stroke": stroke, "stroke-width": str(width)}
        if dashed:
            attrs["stroke-dasharray"] = "14 12"
        ET.SubElement(self.svg, "rect", attrs)
        self.draw.rounded_rectangle((x, y, x+w, y+h), radius=radius, fill=fill,
                                    outline=None if dashed else stroke, width=width)
        if dashed:
            for start, stop, fixed, horizontal in [(x+radius, x+w-radius, y, True),
                                                  (x+radius, x+w-radius, y+h, True),
                                                  (y+radius, y+h-radius, x, False),
                                                  (y+radius, y+h-radius, x+w, False)]:
                p = start
                while p < stop:
                    end = min(p+14, stop)
                    points = ((p, fixed), (end, fixed)) if horizontal else ((fixed, p), (fixed, end))
                    self.draw.line(points, fill=stroke, width=width)
                    p += 26
        self.pdf.setFillColor(toColor(fill))
        self.pdf.setStrokeColor(toColor(stroke))
        self.pdf.setLineWidth(width)
        self.pdf.setDash([14, 12] if dashed else [])
        self.pdf.roundRect(x, H-y-h, w, h, radius, fill=1, stroke=1)
        self.pdf.setDash([])

    def text(self, x, y, value, size=24, color=INK, bold=False, max_width=None, align="left"):
        font = ImageFont.truetype(BOLD if bold else REG, size)
        length = self.draw.textlength(value, font=font)
        if max_width is not None and length > max_width:
            raise ValueError(f"Text exceeds {max_width}px: {value!r} ({length:.1f}px)")
        left = x - length/2 if align == "center" else x
        if left < 0 or left + length > W or y < 0 or y + size*1.25 > H:
            raise ValueError(f"Text outside canvas: {value}")
        self.draw.text((left, y), value, font=font, fill=color, anchor="lt")
        ET.SubElement(self.svg, "text", {
            "x": str(left), "y": str(y), "font-family": "Arial, Helvetica, sans-serif",
            "font-size": str(size), "font-weight": "700" if bold else "400",
            "fill": color, "dominant-baseline": "hanging",
        }).text = value
        self.pdf.setFillColor(toColor(color))
        self.pdf.setFont("DiagramArialBold" if bold else "DiagramArial", size)
        self.pdf.drawString(left, H-y-size*0.9, value)
        self.text_bounds.append({"text": value, "x": round(left, 2), "y": y,
                                 "width": round(length, 2), "height": size*1.25})

    def lines(self, x, y, values, size=24, leading=40, color=MUTED, max_width=None, bold=False):
        for index, value in enumerate(values):
            self.text(x, y+index*leading, value, size, color, bold, max_width)

    def line(self, points, color=GRAY, width=3, dashed=False):
        attrs = {"points": " ".join(f"{x},{y}" for x,y in points), "fill": "none",
                 "stroke": color, "stroke-width": str(width), "stroke-linejoin": "round"}
        if dashed:
            attrs["stroke-dasharray"] = "10 8"
        ET.SubElement(self.svg, "polyline", attrs)
        self.draw.line(points, fill=color, width=width, joint="curve")
        self.pdf.setStrokeColor(toColor(color))
        self.pdf.setLineWidth(width)
        self.pdf.setDash([10,8] if dashed else [])
        path = self.pdf.beginPath()
        path.moveTo(points[0][0], H-points[0][1])
        for x,y in points[1:]:
            path.lineTo(x,H-y)
        self.pdf.drawPath(path)
        self.pdf.setDash([])

    def arrow(self, points, color=GRAY, width=4, both=True):
        self.line(points, color, width)
        ends = [(points[-1], points[-2])]
        if both:
            ends.append((points[0], points[1]))
        for tip, prior in ends:
            dx,dy = tip[0]-prior[0],tip[1]-prior[1]
            length=math.hypot(dx,dy)
            ux,uy = dx/length,dy/length
            a=(tip[0]-ux*15-uy*7,tip[1]-uy*15+ux*7)
            b=(tip[0]-ux*15+uy*7,tip[1]-uy*15-ux*7)
            vertices=[tip,a,b]
            self.draw.polygon(vertices,fill=color)
            ET.SubElement(self.svg,"polygon",{"points":" ".join(f"{x},{y}" for x,y in vertices),"fill":color})
            self.pdf.setFillColor(toColor(color))
            path=self.pdf.beginPath()
            path.moveTo(tip[0],H-tip[1])
            path.lineTo(a[0],H-a[1])
            path.lineTo(b[0],H-b[1])
            path.close()
            self.pdf.drawPath(path,fill=1,stroke=0)

    def save(self):
        self.image.save(OUT/f"{NAME}.png", optimize=True, dpi=(180,180))
        ET.indent(self.svg)
        ET.ElementTree(self.svg).write(OUT/f"{NAME}.svg", encoding="utf-8", xml_declaration=True)
        self.pdf.showPage()
        self.pdf.save()
        (OUT/"layout_validation.json").write_text(json.dumps({
            "canvas": [W,H], "text_items": len(self.text_bounds),
            "checks": ["Every text label fits its declared maximum width", "All text remains inside the canvas"],
            "text_bounds": self.text_bounds,
        },indent=2)+"\n")


d=Diagram()
d.text(65,55,"VEGA | Octobot | Universal Chat",58,bold=True)
d.text(68,142,"Single-Agent High-Level Architecture",34,color=MUTED)
d.text(2925,80,"27 October 2026",24,color=MUTED,align="center")

d.rect(50,235,2490,1300,"#F8FAFC","#9AA8B8",14,3,True)
d.rect(2600,235,550,400,"#FCFAFF","#A89BBB",14,3,True)
d.rect(75,220,260,45,"white","white",0,1)
d.text(90,227,"CITI NETWORK",28,bold=True)
d.rect(2625,220,315,45,"white","white",0,1)
d.text(2640,227,"EXTERNAL CLOUD",28,bold=True)

d.rect(340,335,485,840,"#F0F8FF",BLUE,12)
d.text(375,370,"OPS UI TEAM",28,BLUE,True)
d.rect(890,335,1060,840,"#F7F9FF","#6878E8",12)
d.text(925,370,"SERVICES AI TEAM",28,"#5362C8",True)

d.rect(95,680,195,240,"white","#9BA8B7",10)
d.rect(159,719,66,66,"#E8EDF3","#E8EDF3",33,1)
d.rect(180,729,24,24,"#566575","#566575",12,1)
d.rect(171,759,42,12,"#566575","#566575",6,1)
d.text(192,811,"Operations",30,bold=True,align="center")
d.text(192,855,"User",32,bold=True,align="center")

d.rect(380,440,405,220,"white","#98CFFF",12)
d.text(410,478,"Live VEGA Chat",35,bold=True,max_width=345)
d.lines(410,538,["Universal Chat experience","Session history and streaming","Renders summary + evidence"],23,37,max_width=345)
d.rect(380,790,405,210,"white","#98CFFF",12)
d.text(424,826,"Chat BFF",36,bold=True,max_width=320)
d.lines(410,888,["Authentication + request gateway","Context + userIsoTimestamp"],23,42,max_width=345)

d.rect(930,440,530,575,"white","#6878E8",12)
d.text(964,480,"Universal Chat",42,bold=True,max_width=462)
d.text(964,538,"VEGA / Octobot",30,color=MUTED,max_width=462)
d.rect(964,594,462,52,"#E6F5EF","#BCE5D4",8,2)
d.text(985,610,"ONE END-TO-END AGENT",24,TEAL,True,max_width=420)
d.lines(964,686,["Understand request and context","Resolve dates; validate identifiers",
                 "Plan required AS / TM evidence","Read results; verify conclusions",
                 "Write the full client response","Format the final UI object"],25,45,max_width=462)
d.text(964,976,"Unified reasoning and response",21,color=MUTED,max_width=462)

d.rect(1510,440,400,575,"white","#7FBFB0",12)
d.text(1542,481,"MCP Tool Server",31,bold=True,max_width=336)
d.text(1542,530,"AS fields selected explicitly",22,color=MUTED,max_width=336)
d.rect(1542,568,336,32,"#EAF3FF","#D2E5FD",6,1)
d.text(1555,577,"PARALLEL WHEN INDEPENDENT",16,BLUE,True,max_width=310)
tools=[("Asset Services","query_as_events_entitlements",TEAL,"#EDF9F3"),
       ("Current Transactions","query_tm_current_transactions",AMBER,"#FFF8EB"),
       ("EOD Transactions","query_tm_eod_transactions",AMBER,"#FFF8EB"),
       ("Settlement Instructions","query_tm_settlement_instructions",AMBER,"#FFF8EB")]
for i,(title,tool,color,fill) in enumerate(tools):
    y=620+i*95
    d.rect(1542,y,336,81,fill,color,8,2)
    d.text(1558,y+15,title,23,bold=True,max_width=304)
    d.text(1558,y+52,tool,15,color=MUTED,max_width=304)

d.rect(930,1040,980,95,"#F0F5FF","#C3D6F7",9,2)
d.text(954,1057,"SINGLE-AGENT EXECUTION CONTROLS",22,BLUE,True,max_width=932)
d.text(954,1098,"Once per tool / turn | No agent retries | One page, max 50 rows",23,color=MUTED,max_width=932)

d.rect(2010,335,480,250,"#FAF6FF","#AA83E0",12)
d.text(2046,375,"R2D2 Connector",35,bold=True,max_width=408)
d.lines(2046,440,["Governed model access","COIN authentication"],26,47,max_width=408)
d.text(2046,540,"No direct model-to-data API path",21,color=MUTED,max_width=408)
d.rect(2640,335,470,250,"white","#AA83E0",12)
d.text(2675,375,"Vertex AI",42,bold=True,max_width=400)
d.text(2675,438,"Managed model platform",26,color=MUTED,max_width=400)
d.rect(2675,487,400,60,"#FAF6FF","#DFC8F7",8,2)
d.text(2693,507,"Approved configured model",25,bold=True,max_width=365)

d.rect(2010,690,480,430,"#F6F8FA","#7E8C9B",12)
d.text(2045,724,"ENTERPRISE SERVICES",26,bold=True,max_width=410)
d.rect(2050,780,400,110,"white","#AAB5C2",9,2)
d.text(2075,801,"API Management",31,bold=True,max_width=350)
d.text(2075,848,"Authenticated access",24,color=MUTED,max_width=350)
d.rect(2050,955,400,110,"white","#AAB5C2",9,2)
d.text(2075,977,"Custody Data APIs",30,bold=True,max_width=350)
d.text(2075,1023,"Asset Services | TM",25,color=MUTED,max_width=350)

d.rect(340,1225,2150,255,"#F0F8FF","#98CFFF",12,2)
d.text(375,1257,"PLATFORM DATA & SERVICES",28,BLUE,True,max_width=2055)
for i,label in enumerate(["PostgreSQL","Conversation context","User feedback","Audit logs","Monitoring / evaluation"]):
    x=375+i*415
    d.rect(x,1325,395,95,"white","#D7E4F0",8,2)
    d.text(x+197.5,1360,label,25,bold=True,max_width=355,align="center")

d.arrow([(290,800),(322,800),(322,550),(380,550)],"#657385")
d.arrow([(582,660),(582,790)],BLUE)
d.text(395,712,"Session + context",21,color=MUTED,max_width=174)
d.arrow([(785,895),(930,895)],"#657385")
d.text(798,858,"Request / reply",19,color=MUTED,max_width=133)
d.arrow([(1460,715),(1510,715)],TEAL)
d.arrow([(1910,835),(2050,835)],TEAL)
d.text(1923,798,"Read-only",21,color=MUTED,max_width=125)
d.arrow([(2250,890),(2250,955)],"#657385")
d.arrow([(1335,440),(1335,285),(2250,285),(2250,335)],PURPLE)
d.text(1540,251,"Governed model access",23,PURPLE,max_width=500)
d.arrow([(2490,460),(2640,460)],PURPLE)
d.text(2530,425,"LLM",20,PURPLE,max_width=85)
d.arrow([(930,975),(855,975),(855,1196),(1195,1196),(1195,1225)],"#8C98A7",3)
d.text(1265,1188,"Conversation / feedback / audit",20,color=MUTED,max_width=620)

d.rect(2600,690,550,845,"white","#CFD7E0",12,2)
d.text(2634,728,"RESPONSE & SAFETY CONTRACT",26,bold=True,max_width=482)
d.text(2634,790,"Client-ready output",26,BLUE,True,max_width=482)
d.lines(2634,836,["One final JSON object","Complete summary / email first","AS / TM details, then evidence"],25,38,max_width=482)
d.line([(2634,966),(3116,966)],"#E2E7EE",2)
d.text(2634,997,"Default evidence view",26,TEAL,True,max_width=482)
d.lines(2634,1042,["1-10 total rows: all required","columns; every source row kept",">10 rows: summary + table offer"],25,40,max_width=482)
d.line([(2634,1180),(3116,1180)],"#E2E7EE",2)
d.text(2634,1210,"Explicit table request",26,AMBER,True,max_width=482)
d.lines(2634,1255,["All returned columns and rows","No row filtering or truncation"],25,38,max_width=482)
d.line([(2634,1344),(3116,1344)],"#E2E7EE",2)
d.text(2634,1374,"Dates and data fidelity",26,PURPLE,True,max_width=482)
d.lines(2634,1418,["Zero time -> YYYY-MM-DD","Non-zero times stay unchanged"],25,38,max_width=482)
d.text(2634,1496,"No guessed values or status meaning",22,color=MUTED,max_width=482)

d.save()
print(json.dumps({"output_directory":str(OUT),"files":[f"{NAME}.{extension}" for extension in ["png","svg","pdf"]],"text_items":len(d.text_bounds)}))
