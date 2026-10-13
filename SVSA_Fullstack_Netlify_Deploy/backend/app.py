import os, datetime, secrets
from functools import wraps
from flask import Flask, request, jsonify, g
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
import jwt
from sqlalchemy import UniqueConstraint, Index

app=Flask(__name__)
db_url=os.getenv("DATABASE_URL","sqlite:///svsa_local.db")
if db_url.startswith("postgres://"): db_url=db_url.replace("postgres://","postgresql://",1)
app.config["SQLALCHEMY_DATABASE_URI"]=db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"]=False
app.config["JWT_SECRET"]=os.getenv("JWT_SECRET","local-development-change-me")
db=SQLAlchemy(app)
origin = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173").strip().rstrip("/")
# Allow the configured frontend, local development, and Netlify deploy-preview URLs
# for this site (for example: <deploy-id>--svsaagency1.netlify.app).
netlify_preview_origin = r"^https://([a-z0-9-]+--)?svsaagency1\.netlify\.app$"
CORS(
    app,
    resources={
        r"/api/*": {
            "origins": [origin, "http://localhost:5173", netlify_preview_origin],
            "allow_headers": ["Content-Type", "Authorization"],
            "methods": ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        }
    },
    supports_credentials=False,
    max_age=600,
)

class User(db.Model):
    id=db.Column(db.Integer,primary_key=True); username=db.Column(db.String(80),unique=True,nullable=False)
    display_name=db.Column(db.String(160),nullable=False); role=db.Column(db.String(30),nullable=False)
    employee_id=db.Column(db.String(40)); password_hash=db.Column(db.String(255),nullable=False)
    must_change_password=db.Column(db.Boolean,default=True); active=db.Column(db.Boolean,default=True)
    site_ids=db.Column(db.Text,default="")
class Employee(db.Model):
    id=db.Column(db.String(40),primary_key=True); name=db.Column(db.String(160),nullable=False)
    designation=db.Column(db.String(40),nullable=False); joining_date=db.Column(db.Date,nullable=False)
    phone=db.Column(db.String(40)); email=db.Column(db.String(160)); status=db.Column(db.String(30),default="Active")
    site_ids=db.Column(db.Text,default=""); shift=db.Column(db.String(40)); basic_salary=db.Column(db.Float,default=0)
    food_allowance=db.Column(db.Float,default=0); attendance_bonus=db.Column(db.Float,default=0)
class Site(db.Model):
    id=db.Column(db.String(40),primary_key=True); name=db.Column(db.String(160),nullable=False)
    address=db.Column(db.String(255)); manager_employee_id=db.Column(db.String(40)); required_guards=db.Column(db.Integer,default=0)
    required_supervisors=db.Column(db.Integer,default=0); shift=db.Column(db.String(40)); status=db.Column(db.String(30),default="Active")
class Deployment(db.Model):
    id=db.Column(db.String(40),primary_key=True); employee_id=db.Column(db.String(40),nullable=False); site_id=db.Column(db.String(40),nullable=False)
    role=db.Column(db.String(40),nullable=False); start_date=db.Column(db.Date,nullable=False); end_date=db.Column(db.Date)
    shift=db.Column(db.String(40)); status=db.Column(db.String(30),default="Active")
class Attendance(db.Model):
    id=db.Column(db.Integer,primary_key=True); date=db.Column(db.Date,nullable=False); employee_id=db.Column(db.String(40),nullable=False)
    site_id=db.Column(db.String(40),nullable=False); code=db.Column(db.String(10),nullable=False); shift=db.Column(db.String(40))
    ot_hours=db.Column(db.Float,default=0); remarks=db.Column(db.String(255)); created_by=db.Column(db.Integer)
    __table_args__=(UniqueConstraint("date","employee_id",name="uq_attendance_date_employee"),)
class Advance(db.Model):
    id=db.Column(db.String(40),primary_key=True); employee_id=db.Column(db.String(40),nullable=False); issue_date=db.Column(db.Date,nullable=False)
    amount=db.Column(db.Float,nullable=False); approval_status=db.Column(db.String(20),default="Pending"); recovery_month=db.Column(db.String(7),nullable=False)
    recovered_amount=db.Column(db.Float,default=0); notes=db.Column(db.String(255)); recovered_payroll_id=db.Column(db.String(80))
class Payroll(db.Model):
    id=db.Column(db.String(80),primary_key=True); employee_id=db.Column(db.String(40),nullable=False); month=db.Column(db.String(7),nullable=False)
    basic_salary=db.Column(db.Float,default=0); food_allowance=db.Column(db.Float,default=0); bonus_payable=db.Column(db.Float,default=0)
    ot_pay=db.Column(db.Float,default=0); absence_days=db.Column(db.Integer,default=0); absence_deduction=db.Column(db.Float,default=0)
    pf_deduction=db.Column(db.Float,default=0); esi_deduction=db.Column(db.Float,default=0); advance_recovery=db.Column(db.Float,default=0)
    other_deductions=db.Column(db.Float,default=0); gross_pay=db.Column(db.Float,default=0); net_pay=db.Column(db.Float,default=0)
    status=db.Column(db.String(20),default="Draft"); requires_review=db.Column(db.Boolean,default=False)
    __table_args__=(UniqueConstraint("employee_id","month",name="uq_payroll_employee_month"),)
class Verification(db.Model):
    id=db.Column(db.Integer,primary_key=True); employee_id=db.Column(db.String(40),nullable=False)
    aadhaar_status=db.Column(db.String(30),default="Not checked"); pan_status=db.Column(db.String(30),default="Not checked"); tenth_status=db.Column(db.String(30),default="Not checked")
class Audit(db.Model):
    id=db.Column(db.Integer,primary_key=True); timestamp=db.Column(db.DateTime,default=datetime.datetime.utcnow)
    user_id=db.Column(db.Integer); username=db.Column(db.String(80)); role=db.Column(db.String(30)); module=db.Column(db.String(50))
    record_id=db.Column(db.String(80)); action=db.Column(db.String(80)); summary=db.Column(db.String(500))
class Setting(db.Model):
    key=db.Column(db.String(80),primary_key=True); value=db.Column(db.String(500),nullable=False)

def now_ist_date(): return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=5,minutes=30))).date()
def parse_date(v,required=False):
    if not v:
        if required: raise ValueError("Date is required")
        return None
    return datetime.date.fromisoformat(v[:10])
def asdict(obj):
    out={}
    for c in obj.__table__.columns:
        v=getattr(obj,c.name);out[c.name]=v.isoformat() if isinstance(v,(datetime.date,datetime.datetime)) else v
    return out
def setting(key,default): 
    row=db.session.get(Setting,key); return row.value if row else str(default)
def set_audit(module,record,action,summary):
    u=getattr(g,"user",None);db.session.add(Audit(user_id=u.id if u else None,username=u.username if u else "system",role=u.role if u else "system",module=module,record_id=str(record),action=action,summary=summary))
def token_required(fn):
    @wraps(fn)
    def wrapped(*a,**kw):
        h=request.headers.get("Authorization","")
        if not h.startswith("Bearer "): return jsonify(error="Authentication required"),401
        try:
            payload=jwt.decode(h[7:],app.config["JWT_SECRET"],algorithms=["HS256"]);u=db.session.get(User,int(payload["sub"]))
            if not u or not u.active:return jsonify(error="Account inactive"),401
            g.user=u
        except Exception:return jsonify(error="Invalid or expired session"),401
        return fn(*a,**kw)
    return wrapped
def roles(*allowed):
    def deco(fn):
        @wraps(fn)
        @token_required
        def wrapped(*a,**kw):
            if g.user.role not in allowed:return jsonify(error="Permission denied"),403
            return fn(*a,**kw)
        return wrapped
    return deco
def site_ids_for_user():
    u=g.user
    if u.role=="Director":return None
    return {x.strip() for x in (u.site_ids or "").split(",") if x.strip()}
def authorized_site(site_id):
    allowed=site_ids_for_user()
    return allowed is None or site_id in allowed
def next_id(prefix,model):
    return f"{prefix}-{secrets.token_hex(4).upper()}"
def employee_payload(e):
    d=asdict(e);d["site_ids"]=[x for x in (e.site_ids or "").split(",") if x];return d
def payroll_calc(emp,month):
    rows=Attendance.query.filter_by(employee_id=emp.id).filter(Attendance.date>=datetime.date.fromisoformat(month+"-01")).filter(Attendance.date<=(datetime.date.fromisoformat(month+"-01")+datetime.timedelta(days=40))).all()
    rows=[x for x in rows if x.date.strftime("%Y-%m")==month]
    absent=sum(1 for x in rows if x.code=="A")
    grace=int(setting("absence_grace_days",2));div=max(float(setting("salary_divisor",30)),1)
    chargeable=max(0,absent-grace);absence=round(chargeable*(emp.basic_salary or 0)/div,2)
    bonus=emp.attendance_bonus or 0
    # Advance recovery only once; same-month approved advances, not already tied to payroll.
    payroll_id=f"{emp.id}:{month}"
    advs=Advance.query.filter_by(employee_id=emp.id,recovery_month=month,approval_status="Approved").all()
    adv_amount=sum(max(0,(a.amount or 0)-(a.recovered_amount or 0)) for a in advs if not a.recovered_payroll_id)
    ot_rate=float(setting("ot_rate",0));wo_rate=float(setting("wo_ot_rate",0))
    ot_pay=sum((x.ot_hours or 0)*(wo_rate if x.code=="WO-OT" else ot_rate) for x in rows if x.code in ("OT","WO-OT"))
    basic=emp.basic_salary or 0;food=emp.food_allowance or 0
    pf_rate=float(setting("pf_rate",0));esi_rate=float(setting("esi_rate",0))
    pf=round(basic*pf_rate/100,2);esi=round(basic*esi_rate/100,2)
    gross=round(basic+food+bonus+ot_pay,2);net=round(gross-absence-pf-esi-adv_amount,2)
    return dict(id=payroll_id,employee_id=emp.id,month=month,basic_salary=basic,food_allowance=food,bonus_payable=bonus,ot_pay=ot_pay,absence_days=absent,absence_deduction=absence,pf_deduction=pf,esi_deduction=esi,advance_recovery=adv_amount,other_deductions=0,gross_pay=gross,net_pay=net,status="Draft",requires_review=False)
def ensure_site_limit(employee_id,site_ids):
    manager=Employee.query.filter_by(id=employee_id,designation="Manager").first()
    if manager and len(set(site_ids))>int(setting("manager_site_limit",3)): raise ValueError("Manager may have up to three active sites")
def json_body(): return request.get_json(silent=True) or {}
@app.get("/api/health")
def health(): return jsonify(status="ok",service="svsa-api")
@app.post("/api/auth/login")
def login():
    d=json_body();u=User.query.filter_by(username=d.get("username","")).first()
    if not u or not u.active or not check_password_hash(u.password_hash,d.get("password","")):return jsonify(error="Invalid username or password"),401
    token=jwt.encode({"sub":str(u.id),"exp":datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(hours=8)},app.config["JWT_SECRET"],algorithm="HS256")
    return jsonify(token=token,user={"id":u.id,"username":u.username,"display_name":u.display_name,"role":u.role,"must_change_password":u.must_change_password})
@app.post("/api/auth/change-password")
@token_required
def change_password():
    d=json_body();pw=d.get("new_password","")
    if len(pw)<12:return jsonify(error="Use at least 12 characters for a new password"),400
    g.user.password_hash=generate_password_hash(pw);g.user.must_change_password=False;db.session.commit()
    return jsonify(message="Password changed")
@app.get("/api/dashboard")
@token_required
def dashboard():
    month=request.args.get("month",now_ist_date().strftime("%Y-%m"));allowed=site_ids_for_user()
    q=Attendance.query.filter(Attendance.date>=datetime.date.fromisoformat(month+"-01"),Attendance.date<=datetime.date.fromisoformat(month+"-01")+datetime.timedelta(days=40))
    if allowed is not None:q=q.filter(Attendance.site_id.in_(allowed))
    ar=[x for x in q.all() if x.date.strftime("%Y-%m")==month]
    employees=Employee.query.filter_by(status="Active").all()
    if allowed is not None:employees=[e for e in employees if set((e.site_ids or "").split(","))&allowed]
    payroll=Payroll.query.filter_by(month=month).all()
    if allowed is not None:payroll=[p for p in payroll if (db.session.get(Employee,p.employee_id) and set((db.session.get(Employee,p.employee_id).site_ids or "").split(","))&allowed)]
    return jsonify(total_employees=len(employees),active_sites=Site.query.filter_by(status="Active").count() if allowed is None else Site.query.filter(Site.id.in_(allowed),Site.status=="Active").count(),present=sum(x.code=="P" for x in ar),absent=sum(x.code=="A" for x in ar),weekly_off=sum(x.code=="WO" for x in ar),holiday=sum(x.code=="H" for x in ar),overtime_entries=sum(x.code in ("OT","WO-OT") for x in ar),missing_attendance=0,pending_payroll=sum(p.status in ("Draft","Reviewed") for p in payroll),net_payroll=sum(p.net_pay or 0 for p in payroll),advance_outstanding=sum(max(0,a.amount-a.recovered_amount) for a in Advance.query.all() if a.approval_status=="Approved" and (allowed is None or a.employee_id in {e.id for e in employees})))
@app.get("/api/employees")
@token_required
def employees_list():
    items=Employee.query.all();allowed=site_ids_for_user()
    if allowed is not None:items=[e for e in items if set((e.site_ids or "").split(","))&allowed]
    return jsonify(items=[employee_payload(x) for x in items])
@app.post("/api/employees")
@roles("Director")
def employee_create():
    d=json_body();designation=d.get("designation","Security Guard")
    if not d.get("name") or not d.get("joining_date"):return jsonify(error="Name and joining date are required"),400
    sites=[x.strip() for x in (d.get("site_ids") or "").split(",") if x.strip()]
    if any(not db.session.get(Site,x) for x in sites):return jsonify(error="One or more Site IDs do not exist"),400
    eid=next_id("EMP",Employee)
    salary=45000 if designation=="Director" else float(d.get("basic_salary") or 0)
    e=Employee(id=eid,name=d["name"].strip(),designation=designation,joining_date=parse_date(d["joining_date"],True),phone=d.get("phone"),email=d.get("email"),status=d.get("status","Active"),site_ids=",".join(sites),shift=d.get("shift"),basic_salary=salary,food_allowance=float(d.get("food_allowance") or 0),attendance_bonus=float(d.get("attendance_bonus") or 0))
    try:
        db.session.add(e);db.session.flush()
        if designation=="Manager":
            ensure_site_limit(e.id,sites)
        set_audit("Employee",eid,"Create",f"Created {designation} {e.name}");db.session.commit()
        return jsonify(item=employee_payload(e),message="Employee created"),201
    except Exception as ex:db.session.rollback();return jsonify(error=str(ex)),400
@app.put("/api/employees/<eid>")
@roles("Director")
def employee_update(eid):
    e=db.session.get(Employee,eid)
    if not e:return jsonify(error="Employee not found"),404
    d=json_body()
    for k in ("name","phone","email","status","shift","food_allowance","attendance_bonus"):
        if k in d:setattr(e,k,d[k])
    if "joining_date" in d:e.joining_date=parse_date(d["joining_date"],True)
    if "designation" in d:e.designation=d["designation"]
    if "basic_salary" in d and e.designation!="Director":e.basic_salary=float(d["basic_salary"] or 0)
    if e.designation=="Director":e.basic_salary=45000
    if "site_ids" in d:
        sites=[x.strip() for x in d["site_ids"].split(",") if x.strip()]
        if any(not db.session.get(Site,x) for x in sites):return jsonify(error="Invalid Site ID"),400
        if e.designation=="Manager":ensure_site_limit(e.id,sites)
        e.site_ids=",".join(sites)
    set_audit("Employee",eid,"Update","Employee updated");db.session.commit();return jsonify(item=employee_payload(e))
@app.get("/api/sites")
@token_required
def sites_list():
    items=Site.query.all();allowed=site_ids_for_user()
    if allowed is not None:items=[s for s in items if s.id in allowed]
    return jsonify(items=[asdict(x) for x in items])
@app.post("/api/sites")
@roles("Director")
def site_create():
    d=json_body()
    if not d.get("name"):return jsonify(error="Site name is required"),400
    sid=next_id("SITE",Site);s=Site(id=sid,name=d["name"],address=d.get("address"),manager_employee_id=d.get("manager_employee_id"),required_guards=int(d.get("required_guards") or 0),required_supervisors=int(d.get("required_supervisors") or 0),shift=d.get("shift"),status=d.get("status","Active"))
    if s.manager_employee_id:
        m=db.session.get(Employee,s.manager_employee_id)
        if not m or m.designation!="Manager":return jsonify(error="Assigned employee must be a Manager"),400
        current=Site.query.filter_by(manager_employee_id=m.id,status="Active").count()
        if current>=int(setting("manager_site_limit",3)):return jsonify(error="Manager has reached the active-site limit"),400
    db.session.add(s);db.session.flush()
    if s.manager_employee_id:
        m=db.session.get(Employee,s.manager_employee_id);ids=set(x for x in (m.site_ids or "").split(",") if x);ids.add(s.id);m.site_ids=",".join(ids)
    set_audit("Site",sid,"Create","Created site");db.session.commit();return jsonify(item=asdict(s)),201
@app.put("/api/sites/<sid>")
@roles("Director")
def site_update(sid):
    s=db.session.get(Site,sid)
    if not s:return jsonify(error="Site not found"),404
    d=json_body()
    for k in ("name","address","manager_employee_id","shift","status"):
        if k in d:setattr(s,k,d[k])
    for k in ("required_guards","required_supervisors"):
        if k in d:setattr(s,k,int(d[k] or 0))
    set_audit("Site",sid,"Update","Site updated");db.session.commit();return jsonify(item=asdict(s))
@app.get("/api/deployments")
@token_required
def deployment_list():
    q=Deployment.query.all();allowed=site_ids_for_user()
    if allowed is not None:q=[x for x in q if x.site_id in allowed]
    return jsonify(items=[asdict(x) for x in q])
@app.post("/api/deployments")
@roles("Director")
def deployment_create():
    d=json_body();eid=d.get("employee_id");sid=d.get("site_id")
    if not db.session.get(Employee,eid) or not db.session.get(Site,sid):return jsonify(error="Valid employee and site are required"),400
    dep=Deployment(id=next_id("DEP",Deployment),employee_id=eid,site_id=sid,role=d.get("role","Security Guard"),start_date=parse_date(d.get("start_date"),True),end_date=parse_date(d.get("end_date")),shift=d.get("shift"),status=d.get("status","Active"))
    e=db.session.get(Employee,eid);ids=set(x for x in (e.site_ids or "").split(",") if x);ids.add(sid)
    if e.designation=="Manager":ensure_site_limit(eid,list(ids))
    e.site_ids=",".join(ids);db.session.add(dep);set_audit("Deployment",dep.id,"Create","Created deployment");db.session.commit();return jsonify(item=asdict(dep)),201
@app.get("/api/attendance")
@token_required
def attendance_list():
    q=Attendance.query.order_by(Attendance.date.desc()).all();allowed=site_ids_for_user()
    if allowed is not None:q=[x for x in q if x.site_id in allowed]
    typ=request.args.get("type")
    if typ:
        designation={"guard":"Security Guard","supervisor":"Supervisor","manager":"Manager"}.get(typ)
        if designation:
            ids={e.id for e in Employee.query.filter_by(designation=designation).all()};q=[x for x in q if x.employee_id in ids]
    return jsonify(items=[asdict(x) for x in q])
@app.post("/api/attendance")
@token_required
def attendance_create():
    d=json_body()
    try:
        dt=parse_date(d.get("date") or now_ist_date().isoformat(),True);eid=d.get("employee_id");sid=d.get("site_id");code=d.get("code")
        e=db.session.get(Employee,eid)
        if not e:return jsonify(error="Employee not found"),404
        if not db.session.get(Site,sid):return jsonify(error="Site not found"),404
        if not authorized_site(sid):return jsonify(error="You cannot access this site"),403
        if sid not in (e.site_ids or "").split(","):return jsonify(error="Employee is not assigned to this site"),400
        if code not in ("P","A","WO","H","OT","WO-OT","CL","SL"):return jsonify(error="Invalid attendance code"),400
        row=Attendance(date=dt,employee_id=eid,site_id=sid,code=code,shift=d.get("shift") or e.shift,ot_hours=float(d.get("ot_hours") or 0),remarks=d.get("remarks"),created_by=g.user.id)
        db.session.add(row);db.session.flush();set_audit("Attendance",row.id,"Create",f"{code} attendance for {eid} on {dt}");db.session.commit()
        payroll=Payroll.query.filter_by(employee_id=eid,month=dt.strftime("%Y-%m")).first()
        if payroll and payroll.status in ("Draft","Reviewed"):payroll.requires_review=True;db.session.commit()
        elif payroll:payroll.requires_review=True;db.session.commit()
        return jsonify(item=asdict(row),message="Attendance saved"),201
    except Exception as ex:db.session.rollback();return jsonify(error=str(ex)),400
@app.get("/api/payroll")
@roles("Director")
def payroll_list():return jsonify(items=[asdict(x) for x in Payroll.query.order_by(Payroll.month.desc()).all()])
@app.post("/api/payroll")
@roles("Director")
def payroll_create():
    d=json_body();eid=d.get("employee_id");month=d.get("month")
    e=db.session.get(Employee,eid)
    if not e:return jsonify(error="Employee not found"),404
    if not month or len(month)!=7:return jsonify(error="Payroll month must be YYYY-MM"),400
    existing=Payroll.query.filter_by(employee_id=eid,month=month).first()
    if existing:return jsonify(error="Payroll already exists for this employee and month"),409
    calc=payroll_calc(e,month);calc["ot_pay"]=float(d.get("ot_pay") or calc["ot_pay"]);calc["other_deductions"]=float(d.get("other_deductions") or 0)
    calc["net_pay"]=round(calc["gross_pay"]-calc["absence_deduction"]-calc["pf_deduction"]-calc["esi_deduction"]-calc["advance_recovery"]-calc["other_deductions"],2)
    calc["status"]="Draft"
    p=Payroll(**calc);db.session.add(p);db.session.flush()
    # Mark eligible advances as recovered against this payroll exactly once.
    for a in Advance.query.filter_by(employee_id=eid,recovery_month=month,approval_status="Approved").all():
        if not a.recovered_payroll_id:
            recover=min(max(0,a.amount-a.recovered_amount),max(0,p.advance_recovery))
            if recover>0:a.recovered_amount+=recover;a.recovered_payroll_id=p.id
    set_audit("Payroll",p.id,"Create","Generated payroll draft");db.session.commit();return jsonify(item=asdict(p),message="Payroll draft generated"),201
@app.put("/api/payroll/<pid>")
@roles("Director")
def payroll_update(pid):
    p=db.session.get(Payroll,pid)
    if not p:return jsonify(error="Payroll not found"),404
    d=json_body()
    if p.status=="Paid":return jsonify(error="Paid payroll is locked; use an authorized adjustment workflow"),409
    if p.status=="Approved" and any(k in d for k in ("basic_salary","absence_deduction","advance_recovery","net_pay")):return jsonify(error="Approved payroll is locked for financial edits"),409
    if "status" in d:
        if d["status"] not in ("Draft","Reviewed","Approved","Paid"):return jsonify(error="Invalid payroll status"),400
        p.status=d["status"]
    if p.requires_review and p.status in ("Approved","Paid"):return jsonify(error="Recalculate and review this payroll before approval"),409
    set_audit("Payroll",pid,"Update","Payroll status updated");db.session.commit();return jsonify(item=asdict(p))
@app.get("/api/advances")
@roles("Director")
def advances_list():return jsonify(items=[asdict(x) for x in Advance.query.all()])
@app.post("/api/advances")
@roles("Director")
def advance_create():
    d=json_body();e=db.session.get(Employee,d.get("employee_id"))
    if not e:return jsonify(error="Employee not found"),404
    amount=float(d.get("amount") or 0)
    if amount<=0:return jsonify(error="Advance must be greater than zero"),400
    a=Advance(id=next_id("ADV",Advance),employee_id=e.id,issue_date=parse_date(d.get("issue_date") or now_ist_date().isoformat(),True),amount=amount,approval_status=d.get("approval_status","Pending"),recovery_month=d.get("recovery_month") or now_ist_date().strftime("%Y-%m"),notes=d.get("notes"))
    db.session.add(a);set_audit("Advance",a.id,"Create","Created advance request");db.session.commit();return jsonify(item=asdict(a)),201
@app.get("/api/salary-slips")
@roles("Director")
def salary_slips():return jsonify(items=[asdict(x) for x in Payroll.query.filter(Payroll.status.in_(["Approved","Paid"])).all()])
@app.get("/api/statutory")
@roles("Director")
def statutory():return jsonify(items=[])
@app.get("/api/verification")
@roles("Director")
def verification_list():return jsonify(items=[asdict(x) for x in Verification.query.all()])
@app.post("/api/verification")
@roles("Director")
def verification_create():
    d=json_body();v=Verification(employee_id=d.get("employee_id"),aadhaar_status=d.get("aadhaar_status","Not checked"),pan_status=d.get("pan_status","Not checked"),tenth_status=d.get("tenth_status","Not checked"))
    if not db.session.get(Employee,v.employee_id):return jsonify(error="Employee not found"),404
    db.session.add(v);set_audit("Verification",v.employee_id,"Create","Updated verification status");db.session.commit();return jsonify(item=asdict(v)),201
@app.get("/api/users")
@roles("Director")
def users_list():return jsonify(items=[{"id":u.id,"username":u.username,"display_name":u.display_name,"role":u.role,"employee_id":u.employee_id,"site_ids":u.site_ids,"active":u.active,"must_change_password":u.must_change_password} for u in User.query.all()])
@app.post("/api/users")
@roles("Director")
def users_create():
    d=json_body();username=d.get("username","").strip();pw=d.get("temporary_password","")
    if not username or len(pw)<12:return jsonify(error="Username required; temporary password must be at least 12 characters"),400
    if User.query.filter_by(username=username).first():return jsonify(error="Username already exists"),409
    role=d.get("role","Manager");sites=[x.strip() for x in (d.get("site_ids") or "").split(",") if x.strip()]
    if role=="Manager" and len(sites)>int(setting("manager_site_limit",3)):return jsonify(error="Manager may have up to three sites"),400
    if any(not db.session.get(Site,s) for s in sites):return jsonify(error="Invalid site ID"),400
    u=User(username=username,display_name=d.get("display_name",username),role=role,employee_id=d.get("employee_id"),site_ids=",".join(sites),password_hash=generate_password_hash(pw),must_change_password=True)
    db.session.add(u);db.session.flush();set_audit("User",u.id,"Create",f"Created {role} account");db.session.commit();return jsonify(item={"id":u.id,"username":u.username,"role":u.role},message="Account created; user must change password"),201
@app.get("/api/audit")
@roles("Director")
def audit_list():return jsonify(items=[asdict(x) for x in Audit.query.order_by(Audit.id.desc()).limit(500).all()])
@app.get("/api/reports/attendance")
@token_required
def attendance_report():
    month=request.args.get("month",now_ist_date().strftime("%Y-%m"));allowed=site_ids_for_user()
    rows=Attendance.query.all()
    rows=[x for x in rows if x.date.strftime("%Y-%m")==month and (allowed is None or x.site_id in allowed)]
    return jsonify(items=[asdict(x) for x in rows])
@app.get("/api/settings")
@roles("Director")
def settings_get():return jsonify(settings={k:setting(k,v) for k,v in {"salary_divisor":30,"absence_grace_days":2,"manager_site_limit":3,"director_salary":45000,"ot_rate":0,"wo_ot_rate":0,"pf_rate":0,"esi_rate":0}.items()})
@app.put("/api/settings")
@roles("Director")
def settings_put():
    d=json_body()
    allowed={"salary_divisor","absence_grace_days","manager_site_limit","director_salary","ot_rate","wo_ot_rate","pf_rate","esi_rate"}
    for k,v in d.items():
        if k in allowed:
            row=db.session.get(Setting,k)
            if not row:row=Setting(key=k,value=str(v));db.session.add(row)
            else:row.value=str(v)
    set_audit("Settings","global","Update","Company settings updated");db.session.commit();return jsonify(message="Settings saved")
@app.errorhandler(404)
def not_found(e):return jsonify(error="Endpoint not found"),404
@app.errorhandler(500)
def internal(e):db.session.rollback();return jsonify(error="Internal server error"),500
def seed():
    db.create_all()
    defaults={"salary_divisor":"30","absence_grace_days":"2","manager_site_limit":"3","director_salary":"45000","ot_rate":"0","wo_ot_rate":"0","pf_rate":"0","esi_rate":"0"}
    for k,v in defaults.items():
        if not db.session.get(Setting,k):db.session.add(Setting(key=k,value=v))
    username=os.getenv("BOOTSTRAP_ADMIN_USERNAME","admin");password=os.getenv("BOOTSTRAP_ADMIN_PASSWORD","")
    if password and not User.query.filter_by(username=username).first():
        db.session.add(User(username=username,display_name="SVSA Director",role="Director",password_hash=generate_password_hash(password),must_change_password=True))
    db.session.commit()
with app.app_context():seed()
if __name__=="__main__":app.run(host="0.0.0.0",port=int(os.getenv("PORT",5000)),debug=False)
