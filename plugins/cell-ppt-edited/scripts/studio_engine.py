"""Native structural, path, gradient and rich-text edits. Independently implemented."""
from __future__ import annotations
import hashlib
import json
import math
import time
from base_engine import Engine, EditError, rgb, hex_rgb, absolute_path

EDITING={"auto":0,"corner":1,"smooth":2,"symmetric":3}
SEGMENT={"line":0,"curve":1}
FONT={"name":"Name","name_far_east":"NameFarEast","size":"Size","bold":"Bold","italic":"Italic","underline":"Underline","baseline":"BaselineOffset"}
SHAPES={"rectangle":1,"rounded_rectangle":5,"ellipse":9,"triangle":7,"diamond":4,"hexagon":10,"right_arrow":33}

def number(value, label="value", lower=-1000000, upper=1000000):
    if type(value) not in (int,float) or not math.isfinite(value) or not lower<=value<=upper:
        raise EditError(f"{label} must be a finite number in [{lower}, {upper}].")
    return value

def integer(value,label="index",lower=1,upper=100000):
    if type(value) is not int or not lower<=value<=upper:
        raise EditError(f"Invalid {label}.")
    return value

def fields(value, allowed, required=()):
    if not isinstance(value,dict) or set(value)-set(allowed) or set(required)-set(value):
        raise EditError("Unknown or missing fields.",{"allowed":sorted(allowed),"required":list(required)})

def utf16(text):return len(text.encode("utf-16-le"))//2

def validate_font(font):
    fields(font,set(FONT)|{"color","hyperlink"})
    for key,value in font.items():
        if key in {"name","name_far_east","hyperlink"}:
            if not isinstance(value,str):raise EditError("Font names/hyperlinks must be strings.")
        elif key=="color":rgb(value)
        elif key in {"bold","italic","underline"}:
            if type(value) is not bool:raise EditError("Font flag must be boolean.")
        elif key=="size":number(value,"font size",1,4000)
        elif key=="baseline":number(value,"baseline",-1,1)

def validate_runs(runs):
    if not isinstance(runs,list) or not 1<=len(runs)<=1000:raise EditError("Provide 1..1000 text runs.")
    for run in runs:
        fields(run,{"text","font"},{"text"})
        if not isinstance(run["text"],str) or len(run["text"])>100000 or any(c in run["text"] for c in '\r\n'):
            raise EditError("Runs contain text within one paragraph; paragraph breaks are explicit.")
        validate_font(run.get("font",{}))

def validate_gradient(p):
    fields(p,{"targets","kind","angle","stops"},{"targets","stops"})
    if p.get("kind","linear") not in {"linear","radial","corner"}:raise EditError("Unknown gradient kind.")
    number(p.get("angle",0),"gradient angle",0,360)
    stops=p["stops"]
    if not isinstance(stops,list) or not 2<=len(stops)<=64:raise EditError("Use 2..64 gradient stops.")
    for stop in stops:
        fields(stop,{"position","color","transparency"},{"position","color"})
        number(stop["position"],"stop position",0,1);rgb(stop["color"])
        number(stop.get("transparency",0),"stop transparency",0,1)
    positions=[stop["position"] for stop in stops]
    if positions[0]!=0 or positions[-1]!=1 or any(a>=b for a,b in zip(positions,positions[1:])):
        raise EditError("Gradient stop positions must increase from 0 to 1.")

def validate_path(p):
    if not isinstance(p.get("start"),list) or len(p["start"])!=2:raise EditError("Path start is [x,y].")
    for v in p["start"]:number(v)
    segments=p.get("segments")
    if not isinstance(segments,list) or not 1<=len(segments)<=2000:raise EditError("Use 1..2000 path segments.")
    for seg in segments:
        fields(seg,{"type","points"},{"type","points"})
        if seg["type"] not in {"line","cubic"}:raise EditError("Segment type is line or cubic.")
        expected=2 if seg["type"]=="line" else 6
        if not isinstance(seg["points"],list) or len(seg["points"])!=expected:raise EditError("Wrong segment coordinate count.")
        for v in seg["points"]:number(v)
    if "closed" in p and type(p["closed"]) is not bool:raise EditError("closed must be boolean.")


class StudioEngine(Engine):
    def capabilities(self):
        from pathlib import Path
        return json.loads((Path(__file__).with_name("capabilities.json")).read_text(encoding="utf-8"))

    def status(self):
        return {**super().status(),"product":"cell_ppt_edited","features":["group","ungroup","create","delete","path_nodes","gradient","rich_text"]}

    def target(self,s,slide,target):
        if isinstance(target,str):return self.resolve(s,slide,{"name":target})
        fields(target,{"name","id","path"})
        if len(target)!=1:raise EditError("Specify one name, id or group path.")
        if "path" not in target:return self.resolve(s,slide,target)
        path=target["path"]
        if not isinstance(path,list) or not path or any(not isinstance(v,str) or not v for v in path):raise EditError("path must contain exact group/member names.")
        shape=self.resolve(s,slide,{"name":path[0]})
        for part in path[1:]:
            if int(shape.Type)!=6:raise EditError("A path ancestor is not a group.")
            shape=shape.GroupItems.Item(part)
        return shape

    def _range(self,slide,names):
        import pythoncom
        from win32com.client import VARIANT
        return slide.Shapes.Range(VARIANT(pythoncom.VT_ARRAY|pythoncom.VT_VARIANT,tuple(names)))

    def _exists(self,slide,name):
        try:
            shape=slide.Shapes.Item(name)
            # PowerPoint's named Shapes.Item lookup can find grouped descendants.
            # Structural operations must only treat top-level shapes as present.
            try: parent=shape.ParentGroup
            except Exception: parent=None
            return None if parent is not None else shape
        except Exception:return None

    def nodes(self,shape):
        if int(shape.Type)!=5:raise EditError("Path editing requires a native freeform shape.")
        result=[]
        for i in range(1,shape.Nodes.Count+1):
            node=shape.Nodes.Item(i)
            pts=[[round(float(v),4) for v in point] for point in node.Points]
            try:editing=int(node.EditingType)
            except Exception:editing=None
            try:segment=int(node.SegmentType)
            except Exception:segment=None
            result.append({"index":i,"points":pts,"editing_type":editing,"segment_type":segment})
        digest=hashlib.sha256(json.dumps(result,sort_keys=True).encode()).hexdigest()
        return {"count":len(result),"nodes":result,"hash":digest,"coordinates":"slide points as exposed by PowerPoint; includes Bezier control handles"}

    def gradient_info(self,shape):
        f=shape.Fill
        if int(f.Type)!=3:return {"fill_type":int(f.Type)}
        stops=[]
        for i in range(1,f.GradientStops.Count+1):
            stop=f.GradientStops.Item(i)
            stops.append({"position":round(float(stop.Position),6),"color":hex_rgb(stop.Color.RGB),"transparency":round(float(stop.Transparency),6)})
        style=int(f.GradientStyle)
        angle=round(float(f.GradientAngle),4) if style not in {5,6,7} else None
        return {"fill_type":3,"style":style,"angle":angle,"stops":sorted(stops,key=lambda a:a["position"])}

    def _font_info(self,tr):
        f=tr.Font
        result={"name":str(f.Name),"name_far_east":str(f.NameFarEast),"size":round(float(f.Size),4),"bold":bool(f.Bold),
                "italic":bool(f.Italic),"underline":bool(f.Underline),"baseline":round(float(f.BaselineOffset),4),"color":hex_rgb(f.Color.RGB)}
        try:result["hyperlink"]=str(tr.ActionSettings(1).Hyperlink.Address or "")
        except Exception:result["hyperlink"]=""
        return result

    def rich_info(self,shape):
        if not shape.HasTextFrame:raise EditError("Target has no text frame.")
        tr=shape.TextFrame.TextRange
        runs=[]
        for i in range(1,tr.Runs().Count+1):
            run=tr.Runs(i)
            runs.append({"text":str(run.Text),"start_utf16":int(run.Start)-1,"length_utf16":int(run.Length),"font":self._font_info(run)})
        paragraphs=[]
        for i in range(1,tr.Paragraphs().Count+1):
            p=tr.Paragraphs(i);fmt=p.ParagraphFormat
            paragraphs.append({"text":str(p.Text),"alignment":int(fmt.Alignment),"space_before":float(fmt.SpaceBefore),"space_after":float(fmt.SpaceAfter),"bullet":bool(fmt.Bullet.Visible)})
        return {"text":str(tr.Text),"length_utf16":int(tr.Length),"runs":runs,"paragraphs":paragraphs}

    def inspect_object(self,session_id,slide_index,target,details=None):
        s=self.session(session_id);slide=self.slide(s,slide_index);shape=self.target(s,slide,target)
        result={"path":s["path"],"shape":self.summary(shape,True)}
        details=details or []
        if set(details)-{"nodes","gradient","rich_text","children"}:raise EditError("Unknown detail.")
        if "nodes" in details:result["path_nodes"]=self.nodes(shape)
        if "gradient" in details:result["gradient"]=self.gradient_info(shape)
        if "rich_text" in details:result["rich_text"]=self.rich_info(shape)
        if "children" in details:
            if int(shape.Type)!=6:raise EditError("Target is not a group.")
            result["children"]=[self.summary(shape.GroupItems.Item(i),True) for i in range(1,shape.GroupItems.Count+1)]
        return result

    def _validate_operation(self,op):
        fields(op,{"action","params"},{"action","params"})
        a,p=op["action"],op["params"]
        if a=="create":
            fields(p,{"name","kind","shape_type","left","top","width","height","x1","y1","x2","y2","start","segments","closed","fill_color","line_color","line_width","text","font"},{"name","kind"})
            if not isinstance(p["name"],str) or not p["name"]:raise EditError("A stable shape name is required.")
            if p["kind"] not in {"shape","textbox","line","freeform"}:raise EditError("Unknown object kind.")
            if p["kind"] in {"shape","textbox"}:
                for k in ["left","top","width","height"]:number(p.get(k),k,0.01 if k in {"width","height"} else -1000000)
            if p["kind"]=="shape":
                st=p.get("shape_type","rectangle")
                if st not in SHAPES and not (type(st) is int and 1<=st<=200):raise EditError("Unknown native shape type.")
            if p["kind"]=="line":
                for k in ["x1","y1","x2","y2"]:number(p.get(k),k)
            if p["kind"]=="freeform":validate_path(p)
            for k in ["fill_color","line_color"]:
                if k in p:rgb(p[k])
            if "line_width" in p:number(p["line_width"],"line width",0,1000)
            if "text" in p and not isinstance(p["text"],str):raise EditError("text must be string.")
            validate_font(p.get("font",{}))
        elif a=="group":
            fields(p,{"names","name","allow_z_order_change"},{"names","name"})
            if not isinstance(p["names"],list) or any(not isinstance(n,str) or not n for n in p["names"]) or len(p["names"])<2 or len(set(p["names"]))!=len(p["names"]):raise EditError("Group needs at least two different names.")
            if not isinstance(p["name"],str) or not p["name"]:raise EditError("Group name required.")
            if "allow_z_order_change" in p and type(p["allow_z_order_change"]) is not bool:raise EditError("allow_z_order_change must be boolean.")
        elif a=="ungroup":fields(p,{"target"},{"target"})
        elif a=="delete":
            fields(p,{"names","confirm"},{"names","confirm"})
            if p["confirm"] is not True:raise EditError("Delete requires confirm=true and user authorization.")
            if not isinstance(p["names"],list) or not p["names"] or any(not isinstance(n,str) or not n for n in p["names"]) or len(set(p["names"]))!=len(p["names"]):raise EditError("Specify unique top-level names to delete.")
        elif a=="gradient":
            validate_gradient(p)
            if not isinstance(p["targets"],list) or not p["targets"]:raise EditError("Gradient targets required.")
        elif a=="nodes":
            fields(p,{"target","expected_count","expected_hash","edits"},{"target","expected_count","edits"})
            integer(p["expected_count"])
            if not isinstance(p["edits"],list) or not p["edits"]:raise EditError("Node edits required.")
            for e in p["edits"]:
                fields(e,{"op","index","x","y","editing","segment","points"},{"op","index"});integer(e["index"])
                if e["op"]=="move":number(e.get("x"));number(e.get("y"))
                elif e["op"]=="editing":
                    if e.get("editing") not in EDITING:raise EditError("Invalid editing type.")
                elif e["op"]=="segment":
                    if e.get("segment") not in SEGMENT:raise EditError("Invalid segment type.")
                elif e["op"]=="insert":
                    segment=e.get("segment")
                    if segment not in SEGMENT:raise EditError("Invalid insert segment.")
                    expected=2 if segment=="line" else 6
                    if not isinstance(e.get("points"),list) or len(e["points"])!=expected:raise EditError("Insert needs 2 line or 6 cubic coordinates.")
                    for v in e["points"]:number(v)
                elif e["op"]!="delete":raise EditError("Unsupported node edit.")
        elif a=="rich_text":
            fields(p,{"target","mode","expected_text","edits","paragraphs"},{"target","mode","expected_text"})
            if not isinstance(p["expected_text"],str):raise EditError("expected_text must be string.")
            if p["mode"]=="replace_ranges":
                if not isinstance(p.get("edits"),list) or not p["edits"]:raise EditError("Text edits required.")
                ranges=[]
                for e in p["edits"]:
                    fields(e,{"start","length","runs"},{"start","length","runs"})
                    integer(e["start"],"start",0);integer(e["length"],"length",0);validate_runs(e["runs"])
                    end=e["start"]+e["length"]
                    if end>len(p["expected_text"]):raise EditError("Text range exceeds source text.")
                    if '\r' in p["expected_text"][e["start"]:end]:raise EditError("Range edits preserve paragraph boundaries; use set_paragraphs to rebuild them.")
                    ranges.append((e["start"],end))
                ordered=sorted(ranges)
                if any(a[1]>b[0] or a[0]==b[0] for a,b in zip(ordered,ordered[1:])):raise EditError("Text edits overlap.")
            elif p["mode"]=="set_paragraphs":
                paras=p.get("paragraphs")
                if not isinstance(paras,list) or not 1<=len(paras)<=1000:raise EditError("Paragraphs required.")
                for para in paras:
                    fields(para,{"runs","alignment","space_before","space_after","line_spacing","bullet","level"},{"runs"})
                    validate_runs(para["runs"])
                    if para.get("alignment","left") not in {"left","center","right","justify"}:raise EditError("Invalid alignment.")
                    for key in ["space_before","space_after","line_spacing"]:
                        if key in para:number(para[key],key,0,1000)
                    if "level" in para:integer(para["level"],"level",1,9)
                    if "bullet" in para and type(para["bullet"]) is not bool:raise EditError("bullet must be boolean.")
            else:raise EditError("Unknown rich-text mode.")
        else:raise EditError("Unknown operation action.")

    def _preflight(self,s,slide,operations):
        state={}
        def lookup(name):
            if name in state:
                if state[name] is None:raise EditError(f"Object unavailable after earlier operation: {name}")
                return state[name]
            shape=self._exists(slide,name)
            if shape is None:raise EditError(f"Object not found: {name}")
            return {"object":shape,"type":int(shape.Type)}
        def free(name):
            if name in state:return state[name] is None
            return self._exists(slide,name) is None
        for op in operations:
            self._validate_operation(op)
            a,p=op["action"],op["params"]
            if a=="create":
                if not free(p["name"]):raise EditError("Shape name collision.")
                state[p["name"]]={"type":{"shape":1,"textbox":17,"line":9,"freeform":5}[p["kind"]]}
            elif a=="group":
                if not free(p["name"]):raise EditError("Group name collision.")
                members=[lookup(n) for n in p["names"]]
                if all("object" in m for m in members) and not p.get("allow_z_order_change",False):
                    positions=sorted(int(m["object"].ZOrderPosition) for m in members)
                    if positions[-1]-positions[0]+1!=len(positions):raise EditError("Noncontiguous grouping changes z-order; explicitly set allow_z_order_change=true if intended.")
                for n in p["names"]:state[n]=None
                state[p["name"]]={"type":6,"members":dict(zip(p["names"],members))}
            elif a=="ungroup":
                if not isinstance(p["target"],str):raise EditError("Ungroup uses a top-level group name.")
                group=lookup(p["target"])
                if group["type"]!=6:raise EditError("Ungroup target is not a group.")
                children=group.get("members")
                if children is None:
                    g=group["object"].GroupItems
                    children={str(g.Item(i).Name):{"object":g.Item(i),"type":int(g.Item(i).Type)} for i in range(1,g.Count+1)}
                    if len(children)!=g.Count:raise EditError("Duplicate member names; rename before ungrouping.")
                for name,info in children.items():
                    if not free(name):raise EditError("Ungroup member name collides with a top-level name.")
                    state[name]=info
                state[p["target"]]=None
            elif a=="delete":
                for name in p["names"]:lookup(name);state[name]=None
            else:
                targets=p["targets"] if a=="gradient" else [p["target"]]
                for target in targets:
                    info=lookup(target) if isinstance(target,str) else {"object":self.target(s,slide,target)}
                    shape=info.get("object")
                    if shape is None:
                        if a=="nodes" and info.get("type")!=5:raise EditError("Path editing requires a native freeform.")
                        if a=="rich_text" and info.get("type") in {6,9}:raise EditError("Target has no supported text frame.")
                        continue
                    if a=="nodes":
                        if int(shape.Type)!=5 or shape.Nodes.Count!=p["expected_count"]:raise EditError("Path type/node count guard failed.")
                        if p.get("expected_hash") and self.nodes(shape)["hash"]!=p["expected_hash"]:raise EditError("Path nodes changed since inspection.")
                        if p["edits"][0]["index"]>shape.Nodes.Count:raise EditError("Node index exceeds count.")
                    elif a=="rich_text":
                        if not shape.HasTextFrame or str(shape.TextFrame.TextRange.Text)!=p["expected_text"]:raise EditError("Text changed since inspection.")
                    elif a=="gradient" and int(shape.Type) not in {1,5,6,17}:raise EditError("Gradient requires an AutoShape, freeform, group or text box.")

    def _font(self,tr,font):
        for key,value in font.items():
            if key=="color":tr.Font.Color.RGB=rgb(value)
            elif key=="hyperlink":tr.ActionSettings(1).Hyperlink.Address=value
            else:setattr(tr.Font,FONT[key],(-1 if value else 0) if type(value) is bool else value)

    def _runs(self,tr,runs,start_utf16=0):
        offset=start_utf16
        for run in runs:
            length=utf16(run["text"])
            if length:self._font(tr.Characters(offset+1,length),run.get("font",{}))
            offset+=length

    def _create(self,slide,p):
        kind=p["kind"]
        if kind=="shape":
            st=p.get("shape_type","rectangle");st=SHAPES.get(st,st)
            shape=slide.Shapes.AddShape(st,p["left"],p["top"],p["width"],p["height"])
        elif kind=="textbox":shape=slide.Shapes.AddTextbox(1,p["left"],p["top"],p["width"],p["height"])
        elif kind=="line":shape=slide.Shapes.AddLine(p["x1"],p["y1"],p["x2"],p["y2"])
        else:
            b=slide.Shapes.BuildFreeform(1,*p["start"])
            for segment in p["segments"]:
                cubic=segment["type"]=="cubic"
                b.AddNodes(1 if cubic else 0,1 if cubic else 0,*segment["points"])
            if p.get("closed",False):b.AddNodes(0,0,*p["start"])
            shape=b.ConvertToShape()
        shape.Name=p["name"]
        if "fill_color" in p:shape.Fill.Visible=-1;shape.Fill.Solid();shape.Fill.ForeColor.RGB=rgb(p["fill_color"])
        if "line_color" in p:shape.Line.Visible=-1;shape.Line.ForeColor.RGB=rgb(p["line_color"])
        if "line_width" in p:
            shape.Line.Visible=-1 if p["line_width"] else 0
            if p["line_width"]:shape.Line.Weight=p["line_width"]
        if "text" in p:shape.TextFrame.TextRange.Text=p["text"]
        if p.get("font"):self._font(shape.TextFrame.TextRange,p["font"])
        return self.summary(shape,True)

    def _gradient(self,shape,p):
        f=shape.Fill;stops=p["stops"]
        f.Visible=-1;f.ForeColor.RGB=rgb(stops[0]["color"]);f.BackColor.RGB=rgb(stops[-1]["color"])
        f.TwoColorGradient({"linear":1,"radial":7,"corner":5}[p.get("kind","linear")],1)
        if p.get("kind","linear")=="linear":f.GradientAngle=p.get("angle",0)%360
        gs=f.GradientStops
        while gs.Count>2:gs.Delete(gs.Count)
        for i,stop in [(1,stops[0]),(2,stops[-1])]:
            item=gs.Item(i);item.Color.RGB=rgb(stop["color"]);item.Position=stop["position"];item.Transparency=stop.get("transparency",0)
        for stop in stops[1:-1]:gs.Insert(rgb(stop["color"]),stop["position"],stop.get("transparency",0))
        result=self.gradient_info(shape)
        wanted=[{"position":round(float(v["position"]),6),"color":v["color"].upper(),"transparency":round(float(v.get("transparency",0)),6)} for v in stops]
        if result["stops"]!=wanted:raise EditError("Gradient stop readback mismatch.",{"actual":result,"expected":wanted})
        return result

    def _nodes(self,shape,p):
        if shape.Nodes.Count!=p["expected_count"]:raise EditError("Node count changed.")
        before=self.nodes(shape)
        if p.get("expected_hash") and before["hash"]!=p["expected_hash"]:raise EditError("Path guard changed.")
        for e in p["edits"]:
            index=e["index"]
            if not 1<=index<=shape.Nodes.Count:raise EditError("Current node index out of range; earlier edits can renumber nodes.")
            if e["op"]=="move":shape.Nodes.SetPosition(index,e["x"],e["y"])
            elif e["op"]=="editing":shape.Nodes.SetEditingType(index,EDITING[e["editing"]])
            elif e["op"]=="segment":shape.Nodes.SetSegmentType(index,SEGMENT[e["segment"]])
            elif e["op"]=="insert":
                cubic=e["segment"]=="curve"
                shape.Nodes.Insert(index,1 if cubic else 0,1 if cubic else 0,*e["points"])
            elif e["op"]=="delete":
                if shape.Nodes.Count<=2:raise EditError("Cannot reduce a path below two nodes.")
                shape.Nodes.Delete(index)
        return {"id":int(shape.Id),"before":before,"after":self.nodes(shape)}

    def _rich_text(self,shape,p):
        tr=shape.TextFrame.TextRange;original=str(tr.Text)
        if original!=p["expected_text"]:raise EditError("Text guard changed.")
        if p["mode"]=="replace_ranges":
            expected=original
            for e in sorted(p["edits"],key=lambda v:v["start"],reverse=True):
                start,length=e["start"],e["length"];replacement=''.join(run["text"] for run in e["runs"])
                nstart=utf16(expected[:start]);nlength=utf16(expected[start:start+length])
                if length:tr.Characters(nstart+1,nlength).Text=replacement
                elif start==len(expected):tr.InsertAfter(replacement)
                else:tr.Characters(nstart+1,1).InsertBefore(replacement)
                self._runs(tr,e["runs"],nstart)
                expected=expected[:start]+replacement+expected[start+length:]
        else:
            expected='\r'.join(''.join(r["text"] for r in para["runs"]) for para in p["paragraphs"])
            tr.Text=expected
            offset=0
            for i,para in enumerate(p["paragraphs"],1):
                self._runs(tr,para["runs"],offset)
                pr=tr.Paragraphs(i);fmt=pr.ParagraphFormat
                if "alignment" in para:fmt.Alignment={"left":1,"center":2,"right":3,"justify":4}[para["alignment"]]
                for key,attr in [("space_before","SpaceBefore"),("space_after","SpaceAfter"),("line_spacing","SpaceWithin")]:
                    if key in para:setattr(fmt,attr,para[key])
                if "bullet" in para:fmt.Bullet.Visible=-1 if para["bullet"] else 0
                if "level" in para:pr.IndentLevel=para["level"]
                offset+=utf16(''.join(r["text"] for r in para["runs"]))+1
        if str(tr.Text)!=expected:raise EditError("Rich text readback mismatch.",{"expected":expected,"actual":str(tr.Text)})
        return self.rich_info(shape)

    def edit(self,session_id,slide_index,operations,request_id,save=False,checkpoint_path=None):
        if not isinstance(request_id,str) or not request_id or len(request_id)>200:raise EditError("Stable request_id required.")
        if not isinstance(operations,list) or not 1<=len(operations)<=500:raise EditError("Use 1..500 operations.")
        fingerprint=hashlib.sha256(json.dumps([session_id,slide_index,operations,save,checkpoint_path],sort_keys=True).encode()).hexdigest()
        receipt_key="studio:"+request_id
        if receipt_key in self.receipts:
            signature,result=self.receipts[receipt_key]
            if signature!=fingerprint:raise EditError("Request ID reused with different arguments.")
            return {**result,"replayed":True}
        s=self.session(session_id,write=True);slide=self.slide(s,slide_index)
        self._preflight(s,slide,operations)
        if checkpoint_path:self.save(session_id,checkpoint_path)
        completed=[];start=time.perf_counter();attempted=None
        try:
            for index,operation in enumerate(operations):
                attempted=index;a,p=operation["action"],operation["params"]
                if a=="create":result=self._create(slide,p)
                elif a=="group":
                    group=self._range(slide,p["names"]).Group();group.Name=p["name"]
                    result={"group":self.summary(group,True),"member_count":group.GroupItems.Count}
                elif a=="ungroup":
                    group=self.target(s,slide,p["target"]);members=group.Ungroup()
                    result={"members":[self.summary(members.Item(i),True) for i in range(1,members.Count+1)]}
                elif a=="delete":
                    targets=[self.summary(slide.Shapes.Item(n)) for n in p["names"]]
                    self._range(slide,p["names"]).Delete();result={"deleted":targets}
                elif a=="gradient":result={"targets":[{"name":str((shape:=self.target(s,slide,t)).Name),"gradient":self._gradient(shape,p)} for t in p["targets"]]}
                elif a=="nodes":result=self._nodes(self.target(s,slide,p["target"]),p)
                elif a=="rich_text":result=self._rich_text(self.target(s,slide,p["target"]),p)
                if a in {"create","group","ungroup","delete"}:s["indexes"].clear();s["selection"]=None
                completed.append({"index":index,"action":a,"result":result})
            if save:s["doc"].Save()
            result={"status":"applied","path":s["path"],"operations_applied":len(completed),"results":completed,"saved":bool(save),"shape_count":slide.Shapes.Count,
                    "apply_ms":round((time.perf_counter()-start)*1000,3),"replayed":False}
        except Exception as exc:
            s["indexes"].clear()
            result={"status":"partial_or_uncertain","path":s["path"],"completed":completed,"failed_operation_index":attempted,"error":str(exc),"requires_inspection":True,"saved":False}
        self.receipts[receipt_key]=(fingerprint,result)
        while len(self.receipts)>512:self.receipts.popitem(last=False)
        return result
