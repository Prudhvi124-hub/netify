import os, datetime, secrets, json
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
    site_ids=db.Column(db.Text,default=""); manager_employee_id=db.Column(db.String(40)); shift=db.Column(db.String(40)); basic_salary=db.Column(db.Float,default=0)
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
    amount=db.Column(db.Float,nullable=False); monthly_recovery=db.Column(db.Float,default=0); approval_status=db.Column(db.String(20),default="Pending"); recovery_month=db.Column(db.String(7),nullable=False)
    recovered_amount=db.Column(db.Float,default=0); notes=db.Column(db.String(255)); recovered_payroll_id=db.Column(db.String(80))
class Payroll(db.Model):
    id=db.Column(db.String(80),primary_key=True); employee_id=db.Column(db.String(40),nullable=False); month=db.Column(db.String(7),nullable=False)
    basic_salary=db.Column(db.Float,default=0); food_allowance=db.Column(db.Float,default=0); bonus_payable=db.Column(db.Float,default=0)
    ot_pay=db.Column(db.Float,default=0); absence_days=db.Column(db.Integer,default=0); absence_deduction=db.Column(db.Float,default=0)
    pf_deduction=db.Column(db.Float,default=0); esi_deduction=db.Column(db.Float,default=0); advance_recovery=db.Column(db.Float,default=0)
    other_deductions=db.Column(db.Float,default=0); gross_pay=db.Column(db.Float,default=0); net_pay=db.Column(db.Float,default=0)
    status=db.Column(db.String(20),default="Draft"); requires_review=db.Column(db.Boolean,default=False)
    monthly_basic_salary=db.Column(db.Float,default=0); monthly_food_allowance=db.Column(db.Float,default=0)
    daily_rate=db.Column(db.Float,default=0); present_days=db.Column(db.Integer,default=0)
    paid_days=db.Column(db.Integer,default=0); recorded_days=db.Column(db.Integer,default=0)
    advance_recovery_details=db.Column(db.Text,default="[]")
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
    if u.role=="Director": return None
    ids={x.strip() for x in (u.site_ids or "").split(",") if x.strip()}
    if u.role=="Manager" and u.employee_id:
        ids.update(s.id for s in Site.query.filter_by(manager_employee_id=u.employee_id,status="Active").all())
    return ids

def authorized_site(site_id):
    allowed=site_ids_for_user()
    return allowed is None or site_id in allowed

def next_id(prefix,model):
    return f"{prefix}-{secrets.token_hex(4).upper()}"

def employee_payload(e):
    d=asdict(e)
    d["site_ids"]=[x for x in (e.site_ids or "").split(",") if x]
    manager=db.session.get(Employee,e.manager_employee_id) if e.manager_employee_id else None
    d["manager_name"]=manager.name if manager else ""
    d["site_names"]=[site.name for sid in d["site_ids"] if (site:=db.session.get(Site,sid))]
    return d

def labelled_record(obj):
    """Serialize a record and add human-readable related names for tables/reports."""
    d=asdict(obj)
    if isinstance(obj,Payroll):
        try:
            recovery_plan=json.loads(obj.advance_recovery_details or "[]")
            labels=[]
            for item in recovery_plan:
                advance=db.session.get(Advance,item.get("advance_id"))
                name=(advance.id if advance else item.get("advance_id","Advance"))
                labels.append(f"{name}: ₹{float(item.get('amount') or 0):,.2f}")
            d["advance_recovery_details"]="; ".join(labels) if labels else "None"
        except (TypeError,ValueError,AttributeError):
            d["advance_recovery_details"]=obj.advance_recovery_details or "None"
    eid=d.get("employee_id")
    sid=d.get("site_id")
    emp=db.session.get(Employee,eid) if eid else None
    site=db.session.get(Site,sid) if sid else None
    d["employee_name"]=emp.name if emp else ""
    d["site_name"]=site.name if site else ""
    mid=d.get("manager_employee_id")
    manager=db.session.get(Employee,mid) if mid else None
    d["manager_name"]=manager.name if manager else ""
    if "site_ids" in d:
        ids=[x.strip() for x in (d.get("site_ids") or "").split(",") if x.strip()] if isinstance(d.get("site_ids"),str) else d.get("site_ids") or []
        d["site_names"]=[site.name for sid in ids if (site:=db.session.get(Site,sid))]
    return d

def advance_recovery_plan(employee_id,month,max_total):
    """Plan approved advance instalments without exceeding available take-home pay."""
    plan=[]
    remaining=max(0.0,float(max_total or 0))
    advances=Advance.query.filter(
        Advance.employee_id==employee_id,
        Advance.recovery_month<=month,
        Advance.approval_status=="Approved"
    ).order_by(Advance.issue_date.asc()).all()
    for advance in advances:
        if remaining<=0:break
        outstanding=max(0.0,float(advance.amount or 0)-float(advance.recovered_amount or 0))
        cap=max(0.0,float(advance.monthly_recovery or 0) or float(advance.amount or 0))
        recover=round(min(outstanding,cap,remaining),2)
        if recover>0:
            plan.append({"advance_id":advance.id,"amount":recover})
            remaining=round(remaining-recover,2)
    return plan

def payroll_calc(emp,month):
    first=datetime.date.fromisoformat(month+"-01")
    next_month=(first.replace(day=28)+datetime.timedelta(days=4)).replace(day=1)
    rows=Attendance.query.filter(Attendance.employee_id==emp.id,Attendance.date>=first,Attendance.date<next_month).all()
    # P, WO, H, OT, WO-OT, CL and SL count as paid days. A is an unpaid day.
    paid_codes={"P","WO","H","OT","WO-OT","CL","SL"}
    present_codes={"P","OT","WO-OT"}
    present_days=sum(1 for row in rows if row.code in present_codes)
    absent=sum(1 for row in rows if row.code=="A")
    paid_days=sum(1 for row in rows if row.code in paid_codes)
    recorded_days=len(rows)
    divisor=max(float(setting("salary_divisor",30)),1)
    monthly_basic=round(float(emp.basic_salary or 0),2)
    monthly_food=round(float(emp.food_allowance or 0),2)
    daily_rate=round((monthly_basic+monthly_food)/divisor,2)
    earned_basic=round(monthly_basic/divisor*paid_days,2)
    earned_food=round(monthly_food/divisor*paid_days,2)
    # This is the value of wages not earned because absence days are unpaid.
    # It is informational: earned salary is already prorated by paid_days, so do not subtract it twice.
    absence_loss=round(absent*daily_rate,2)
    bonus=float(emp.attendance_bonus or 0)
    if absent>=3: bonus=0
    elif absent==2: bonus=max(0,bonus-float(setting("bonus_cut_two_absences",800)))
    ot_rate=float(setting("ot_rate",0));wo_rate=float(setting("wo_ot_rate",0))
    ot_pay=round(sum((row.ot_hours or 0)*(wo_rate if row.code=="WO-OT" else ot_rate) for row in rows if row.code in ("OT","WO-OT")),2)
    pf=round(earned_basic*float(setting("pf_rate",0))/100,2)
    esi=round(earned_basic*float(setting("esi_rate",0))/100,2)
    gross=round(earned_basic+earned_food+bonus+ot_pay,2)
    other_deductions=0.0
    max_advance_recovery=max(0.0,gross-pf-esi-other_deductions)
    plan=advance_recovery_plan(emp.id,month,max_advance_recovery)
    adv_amount=round(sum(item["amount"] for item in plan),2)
    net=round(gross-pf-esi-adv_amount-other_deductions,2)
    return dict(
        id=f"{emp.id}:{month}",employee_id=emp.id,month=month,
        monthly_basic_salary=monthly_basic,monthly_food_allowance=monthly_food,daily_rate=daily_rate,
        present_days=present_days,paid_days=paid_days,recorded_days=recorded_days,
        basic_salary=earned_basic,food_allowance=earned_food,bonus_payable=bonus,ot_pay=ot_pay,
        absence_days=absent,absence_deduction=absence_loss,pf_deduction=pf,esi_deduction=esi,
        advance_recovery=adv_amount,advance_recovery_details=json.dumps(plan),
        other_deductions=other_deductions,gross_pay=gross,net_pay=net,status="Draft",requires_review=False
    )

def ensure_site_limit(employee_id,site_ids):
    manager=Employee.query.filter_by(id=employee_id,designation="Manager").first()
    if manager and len(set(site_ids))>int(setting("manager_site_limit",20)):
        raise ValueError(f"Manager may have up to {setting('manager_site_limit',20)} active sites")

def manager_site_ids(employee_id):
    return {s.id for s in Site.query.filter_by(manager_employee_id=employee_id,status="Active").all()}

def migrate_additive_columns():
    # create_all does not add columns to tables already present in PostgreSQL/SQLite.
    from sqlalchemy import inspect, text
    try:
        inspector=inspect(db.engine)
        if "employee" in inspector.get_table_names():
            cols={c["name"] for c in inspector.get_columns("employee")}
            if "manager_employee_id" not in cols:
                db.session.execute(text("ALTER TABLE employee ADD COLUMN manager_employee_id VARCHAR(40)"))
                db.session.commit()
        if "advance" in inspector.get_table_names():
            cols={c["name"] for c in inspector.get_columns("advance")}
            if "monthly_recovery" not in cols:
                db.session.execute(text("ALTER TABLE advance ADD COLUMN monthly_recovery FLOAT DEFAULT 0"))
                db.session.commit()
        if "payroll" in inspector.get_table_names():
            cols={c["name"] for c in inspector.get_columns("payroll")}
            additions={
                "monthly_basic_salary":"FLOAT DEFAULT 0",
                "monthly_food_allowance":"FLOAT DEFAULT 0",
                "daily_rate":"FLOAT DEFAULT 0",
                "present_days":"INTEGER DEFAULT 0",
                "paid_days":"INTEGER DEFAULT 0",
                "recorded_days":"INTEGER DEFAULT 0",
                "advance_recovery_details":"TEXT DEFAULT '[]'",
            }
            for column, sql_type in additions.items():
                if column not in cols:
                    db.session.execute(text(f"ALTER TABLE payroll ADD COLUMN {column} {sql_type}"))
            db.session.commit()
    except Exception:
        db.session.rollback()

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
    if allowed is not None:
        if g.user.role=="Manager": employees=[e for e in employees if e.designation in ("Security Guard","Supervisor") and e.manager_employee_id==g.user.employee_id]
        else: employees=[e for e in employees if set((e.site_ids or "").split(","))&allowed]
    payroll=Payroll.query.filter_by(month=month).all() if g.user.role=="Director" else []
    if allowed is not None:payroll=[p for p in payroll if (db.session.get(Employee,p.employee_id) and set((db.session.get(Employee,p.employee_id).site_ids or "").split(","))&allowed)]
    return jsonify(total_employees=len(employees),active_sites=Site.query.filter_by(status="Active").count() if allowed is None else Site.query.filter(Site.id.in_(allowed),Site.status=="Active").count(),present=sum(x.code=="P" for x in ar),absent=sum(x.code=="A" for x in ar),weekly_off=sum(x.code=="WO" for x in ar),holiday=sum(x.code=="H" for x in ar),overtime_entries=sum(x.code in ("OT","WO-OT") for x in ar),missing_attendance=0,pending_payroll=sum(p.status in ("Draft","Reviewed") for p in payroll),net_payroll=sum(p.net_pay or 0 for p in payroll),advance_outstanding=(sum(max(0,a.amount-a.recovered_amount) for a in Advance.query.all() if a.approval_status=="Approved" and (allowed is None or a.employee_id in {e.id for e in employees})) if g.user.role=="Director" else 0))
@app.get("/api/employees")
@token_required
def employees_list():
    items=Employee.query.all();allowed=site_ids_for_user()
    if allowed is not None:
        if g.user.role=="Manager": items=[e for e in items if e.designation in ("Security Guard","Supervisor") and e.manager_employee_id==g.user.employee_id and bool({x.strip() for x in (e.site_ids or "").split(",") if x.strip()}&allowed)]
        else: items=[e for e in items if set((e.site_ids or "").split(","))&allowed]
    if g.user.role!="Director":
        return jsonify(items=[{**employee_payload(e),"basic_salary":None,"food_allowance":None,"attendance_bonus":None,"phone":None,"email":None} for e in items])
    return jsonify(items=[employee_payload(x) for x in items])
@app.post("/api/employees")
@roles("Director")
def employee_create():
    d=json_body();designation=d.get("designation","Security Guard")
    if not d.get("name") or not d.get("joining_date"):return jsonify(error="Name and joining date are required"),400
    sites=[x.strip() for x in (d.get("site_ids") or "").split(",") if x.strip()]
    if any(not db.session.get(Site,x) for x in sites):return jsonify(error="One or more Site IDs do not exist"),400
    manager_id=(d.get("manager_employee_id") or "").strip() or None
    if manager_id:
        manager=db.session.get(Employee,manager_id)
        if not manager or manager.designation!="Manager": return jsonify(error="Select a valid Manager employee"),400
        if designation not in ("Security Guard","Supervisor"): return jsonify(error="Only Guards and Supervisors can be assigned to a Manager"),400
    eid=next_id("EMP",Employee)
    salary=float(setting("director_salary",45000)) if designation=="Director" else float(d.get("basic_salary") or 0)
    e=Employee(id=eid,name=d["name"].strip(),designation=designation,joining_date=parse_date(d["joining_date"],True),phone=d.get("phone"),email=d.get("email"),status=d.get("status","Active"),site_ids=",".join(sites),manager_employee_id=manager_id,shift=d.get("shift"),basic_salary=salary,food_allowance=float(d.get("food_allowance") or 0),attendance_bonus=float(d.get("attendance_bonus") or 0))
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
    if "manager_employee_id" in d:
        mid=(d.get("manager_employee_id") or "").strip() or None
        manager=db.session.get(Employee,mid) if mid else None
        if mid and (not manager or manager.designation!="Manager"): return jsonify(error="Select a valid Manager employee"),400
        if mid and e.designation not in ("Security Guard","Supervisor"): return jsonify(error="Only Guards and Supervisors can be assigned to a Manager"),400
        e.manager_employee_id=mid
    if "basic_salary" in d and e.designation!="Director":e.basic_salary=float(d["basic_salary"] or 0)
    if e.designation=="Director":e.basic_salary=45000
    if "site_ids" in d:
        sites=[x.strip() for x in d["site_ids"].split(",") if x.strip()]
        if any(not db.session.get(Site,x) for x in sites):return jsonify(error="Invalid Site ID"),400
        if e.designation=="Manager":ensure_site_limit(e.id,sites)
        e.site_ids=",".join(sites)
    set_audit("Employee",eid,"Update","Employee updated");db.session.commit();return jsonify(item=employee_payload(e))
@app.delete("/api/employees/<eid>")
@roles("Director")
def employee_delete(eid):
    e=db.session.get(Employee,eid)
    if not e:return jsonify(error="Employee not found"),404
    if e.designation=="Director":
        return jsonify(error="Director employee records cannot be deleted"),409
    if User.query.filter_by(id=g.user.id,employee_id=eid).first():
        return jsonify(error="You cannot delete the employee record linked to your signed-in Director account"),409
    try:
        # Employee deletion is a Director-only permanent cascade.
        # Clear manager/site references first, then remove dependent records.
        for subordinate in Employee.query.filter_by(manager_employee_id=eid).all():
            subordinate.manager_employee_id=None
        for site in Site.query.filter_by(manager_employee_id=eid).all():
            site.manager_employee_id=None
        for account in User.query.filter_by(employee_id=eid).all():
            db.session.delete(account)
        for attendance in Attendance.query.filter_by(employee_id=eid).all():
            db.session.delete(attendance)
        for payroll in Payroll.query.filter_by(employee_id=eid).all():
            db.session.delete(payroll)
        for advance in Advance.query.filter_by(employee_id=eid).all():
            db.session.delete(advance)
        for deployment in Deployment.query.filter_by(employee_id=eid).all():
            db.session.delete(deployment)
        for verification in Verification.query.filter_by(employee_id=eid).all():
            db.session.delete(verification)
        db.session.delete(e)
        set_audit("Employee",eid,"Delete","Permanently deleted employee and related records")
        db.session.commit()
        return jsonify(message="Employee and all related records permanently deleted",deleted=True)
    except Exception as ex:
        db.session.rollback()
        return jsonify(error="Could not delete employee safely",details=str(ex)),400

@app.get("/api/sites")
@token_required
def sites_list():
    items=Site.query.all();allowed=site_ids_for_user()
    if allowed is not None:
        if g.user.role=="Manager": items=[site for site in items if site.manager_employee_id==g.user.employee_id and site.status=="Active"]
        else: items=[site for site in items if site.id in allowed]
    return jsonify(items=[{**asdict(x),"manager_name":(db.session.get(Employee,x.manager_employee_id).name if x.manager_employee_id and db.session.get(Employee,x.manager_employee_id) else "")} for x in items])
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
        if current>=int(setting("manager_site_limit",20)):return jsonify(error="Manager has reached the 20-site limit"),400
    db.session.add(s);db.session.flush()
    if s.manager_employee_id:
        m=db.session.get(Employee,s.manager_employee_id);ids=set(x for x in (m.site_ids or "").split(",") if x);ids.add(s.id);m.site_ids=",".join(ids)
    set_audit("Site",sid,"Create","Created site");db.session.commit();return jsonify(item={**asdict(s),"manager_name":(db.session.get(Employee,s.manager_employee_id).name if s.manager_employee_id and db.session.get(Employee,s.manager_employee_id) else "")}),201
@app.put("/api/sites/<sid>")
@roles("Director")
def site_update(sid):
    s=db.session.get(Site,sid)
    if not s:return jsonify(error="Site not found"),404
    d=json_body()
    for k in ("name","address","shift","status"):
        if k in d:setattr(s,k,d[k])
    if "manager_employee_id" in d:
        mid=(d.get("manager_employee_id") or "").strip() or None
        m=db.session.get(Employee,mid) if mid else None
        if mid and (not m or m.designation!="Manager"): return jsonify(error="Assigned employee must be a Manager"),400
        if mid and mid!=s.manager_employee_id:
            count=Site.query.filter_by(manager_employee_id=mid,status="Active").filter(Site.id!=sid).count()
            if count>=int(setting("manager_site_limit",20)): return jsonify(error="Manager has reached the 20-site limit"),400
        s.manager_employee_id=mid
    for k in ("required_guards","required_supervisors"):
        if k in d:setattr(s,k,int(d[k] or 0))
    set_audit("Site",sid,"Update","Site updated");db.session.commit();return jsonify(item={**asdict(s),"manager_name":(db.session.get(Employee,s.manager_employee_id).name if s.manager_employee_id and db.session.get(Employee,s.manager_employee_id) else "")})
@app.delete("/api/sites/<sid>")
@roles("Director")
def site_delete(sid):
    site=db.session.get(Site,sid)
    if not site:return jsonify(error="Site not found"),404
    try:
        attendance=Attendance.query.filter_by(site_id=sid).all()
        affected={(x.employee_id,x.date.strftime("%Y-%m")) for x in attendance}
        for row in attendance:db.session.delete(row)
        for row in Deployment.query.filter_by(site_id=sid).all():db.session.delete(row)
        for emp in Employee.query.all():
            ids=[x.strip() for x in (emp.site_ids or "").split(",") if x.strip() and x.strip()!=sid]
            emp.site_ids=",".join(ids)
        for account in User.query.all():
            ids=[x.strip() for x in (account.site_ids or "").split(",") if x.strip() and x.strip()!=sid]
            account.site_ids=",".join(ids)
        db.session.flush()
        for eid,month in affected:
            payroll=Payroll.query.filter_by(employee_id=eid,month=month).first()
            if payroll:payroll.requires_review=True
        db.session.delete(site)
        set_audit("Site",sid,"Delete","Permanently deleted site and linked attendance/deployment records")
        db.session.commit()
        return jsonify(message="Site and linked attendance/deployment records permanently deleted",deleted=True)
    except Exception as ex:
        db.session.rollback()
        return jsonify(error="Could not delete site",details=str(ex)),400

@app.get("/api/deployments")
@token_required
def deployment_list():
    q=Deployment.query.all();allowed=site_ids_for_user()
    if allowed is not None:q=[x for x in q if x.site_id in allowed]
    return jsonify(items=[labelled_record(x) for x in q])
@app.delete("/api/deployments/<did>")
@roles("Director")
def deployment_delete(did):
    row=db.session.get(Deployment,did)
    if not row:return jsonify(error="Deployment not found"),404
    db.session.delete(row)
    set_audit("Site Deployment",did,"Delete","Permanently deleted deployment record")
    db.session.commit()
    return jsonify(message="Deployment deleted",deleted=True)

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
    if g.user.role=="Manager":
        q=[x for x in q if (db.session.get(Employee,x.employee_id) and db.session.get(Employee,x.employee_id).manager_employee_id==g.user.employee_id and db.session.get(Site,x.site_id) and db.session.get(Site,x.site_id).manager_employee_id==g.user.employee_id)]
    typ=request.args.get("type")
    if typ:
        designation={"guard":"Security Guard","supervisor":"Supervisor","manager":"Manager"}.get(typ)
        if designation:
            ids={e.id for e in Employee.query.filter_by(designation=designation).all()};q=[x for x in q if x.employee_id in ids]
    return jsonify(items=[labelled_record(x) for x in q])
@app.post("/api/attendance")
@roles("Director","Manager")
def attendance_create():
    d=json_body()
    try:
        dt=parse_date(d.get("date") or now_ist_date().isoformat(),True);eid=d.get("employee_id");sid=d.get("site_id");code=d.get("code")
        e=db.session.get(Employee,eid)
        if not e:return jsonify(error="Employee not found"),404
        if not db.session.get(Site,sid):return jsonify(error="Site not found"),404
        if not authorized_site(sid):return jsonify(error="You cannot access this site"),403
        site=db.session.get(Site,sid)
        if g.user.role=="Manager":
            if not g.user.employee_id or site.manager_employee_id!=g.user.employee_id:
                return jsonify(error="Managers can record attendance only for their assigned sites"),403
            if e.designation not in ("Security Guard","Supervisor") or e.manager_employee_id!=g.user.employee_id:
                return jsonify(error="Employee is not assigned to your Manager account"),403
        elif g.user.role!="Director": return jsonify(error="Only Director or assigned Manager can record attendance"),403
        assigned_site_ids={x.strip() for x in (e.site_ids or "").split(",") if x.strip()}
        if sid not in assigned_site_ids and not Deployment.query.filter_by(employee_id=eid,site_id=sid,status="Active").first():
            return jsonify(error="Employee is not assigned to this site. Assign the site in Employee Master first."),400
        if code not in ("P","A","WO","H","OT","WO-OT","CL","SL"):return jsonify(error="Invalid attendance code"),400
        row=Attendance.query.filter_by(date=dt,employee_id=eid).first()
        created=row is None
        if row is None:
            row=Attendance(date=dt,employee_id=eid,site_id=sid,code=code,shift=d.get("shift") or e.shift,ot_hours=float(d.get("ot_hours") or 0),remarks=d.get("remarks"),created_by=g.user.id)
            db.session.add(row)
        else:
            # One row per employee per date is the current schema rule; update rather than duplicate.
            row.site_id=sid;row.code=code;row.shift=d.get("shift") or e.shift
            row.ot_hours=float(d.get("ot_hours") or 0);row.remarks=d.get("remarks");row.created_by=g.user.id
        db.session.flush();set_audit("Attendance",row.id,"Create" if created else "Update",f"{code} attendance for {eid} on {dt}");db.session.commit()
        payroll=Payroll.query.filter_by(employee_id=eid,month=dt.strftime("%Y-%m")).first()
        if payroll:payroll.requires_review=True;db.session.commit()
        return jsonify(item=labelled_record(row),message="Attendance saved" if created else "Attendance already existed; record updated"),201 if created else 200
    except Exception as ex:db.session.rollback();return jsonify(error=str(ex)),400
@app.delete("/api/attendance/<int:aid>")
@roles("Director")
def attendance_delete(aid):
    row=db.session.get(Attendance,aid)
    if not row:return jsonify(error="Attendance record not found"),404
    payroll=Payroll.query.filter_by(employee_id=row.employee_id,month=row.date.strftime("%Y-%m")).first()
    db.session.delete(row)
    if payroll:payroll.requires_review=True
    set_audit("Attendance",aid,"Delete","Permanently deleted attendance record")
    db.session.commit()
    return jsonify(message="Attendance deleted; related payroll marked for review" if payroll else "Attendance deleted",deleted=True)

@app.get("/api/payroll")
@roles("Director")
def payroll_list():return jsonify(items=[labelled_record(x) for x in Payroll.query.order_by(Payroll.month.desc()).all()])
@app.post("/api/payroll")
@roles("Director")
def payroll_create():
    d=json_body();eid=d.get("employee_id");month=d.get("month")
    e=db.session.get(Employee,eid)
    if not e:return jsonify(error="Employee not found"),404
    if not month or len(month)!=7 or month[4]!="-":return jsonify(error="Payroll month must be YYYY-MM"),400
    try:
        datetime.date.fromisoformat(month+"-01")
    except ValueError:
        return jsonify(error="Payroll month must be a valid YYYY-MM month"),400
    existing=Payroll.query.filter_by(employee_id=eid,month=month).first()
    if existing:return jsonify(error="Payroll already exists for this employee and month. Use Recalculate on a Draft/Reviewed payroll."),409
    calc=payroll_calc(e,month)
    if d.get("ot_pay") not in (None,""):calc["ot_pay"]=max(0,float(d["ot_pay"]))
    calc["other_deductions"]=max(0,float(d.get("other_deductions") or 0))
    calc["gross_pay"]=round(calc["basic_salary"]+calc["food_allowance"]+calc["bonus_payable"]+calc["ot_pay"],2)
    available=max(0,calc["gross_pay"]-calc["pf_deduction"]-calc["esi_deduction"]-calc["other_deductions"])
    plan=advance_recovery_plan(eid,month,available)
    calc["advance_recovery_details"]=json.dumps(plan)
    calc["advance_recovery"]=round(sum(item["amount"] for item in plan),2)
    calc["net_pay"]=round(calc["gross_pay"]-calc["pf_deduction"]-calc["esi_deduction"]-calc["advance_recovery"]-calc["other_deductions"],2)
    calc["status"]="Draft";calc["requires_review"]=False
    p=Payroll(**calc);db.session.add(p);db.session.flush()
    for item in plan:
        advance=db.session.get(Advance,item["advance_id"])
        if advance:
            advance.recovered_amount=round(float(advance.recovered_amount or 0)+item["amount"],2)
            advance.recovered_payroll_id=p.id
    set_audit("Payroll",p.id,"Create",f"Generated attendance-based payroll with {p.paid_days} paid days")
    db.session.commit()
    return jsonify(item=labelled_record(p),message="Payroll draft generated from attendance"),201
@app.post("/api/payroll/<pid>/recalculate")
@roles("Director")
def payroll_recalculate(pid):
    p=db.session.get(Payroll,pid)
    if not p:return jsonify(error="Payroll not found"),404
    if p.status in ("Approved","Paid"):
        return jsonify(error="Approved or Paid payroll is locked; use an authorized adjustment workflow"),409
    later=Payroll.query.filter(Payroll.employee_id==p.employee_id,Payroll.month>p.month).first()
    if later:return jsonify(error="Recalculate only the latest payroll for this employee so advance recoveries remain consistent"),409
    try:
        old_plan=json.loads(p.advance_recovery_details or "[]")
    except (TypeError,ValueError):
        old_plan=[]
    if not old_plan and float(p.advance_recovery or 0)>0:
        return jsonify(error="This older payroll has no advance recovery breakdown. It cannot be recalculated safely; review its advance ledger manually first."),409
    # Reverse only the previous payroll's recorded instalments before calculating again.
    for item in old_plan:
        advance=db.session.get(Advance,item.get("advance_id"))
        if advance:
            amount=max(0,float(item.get("amount") or 0))
            advance.recovered_amount=round(max(0,float(advance.recovered_amount or 0)-amount),2)
            if advance.recovered_payroll_id==p.id:advance.recovered_payroll_id=None
    emp=db.session.get(Employee,p.employee_id)
    if not emp:return jsonify(error="Employee not found"),404
    calc=payroll_calc(emp,p.month)
    # Recalculation uses the current attendance and configured OT rates, preserving only other authorized deductions.
    calc["other_deductions"]=max(0,float(p.other_deductions or 0))
    available=max(0,calc["gross_pay"]-calc["pf_deduction"]-calc["esi_deduction"]-calc["other_deductions"])
    plan=advance_recovery_plan(emp.id,p.month,available)
    calc["advance_recovery_details"]=json.dumps(plan)
    calc["advance_recovery"]=round(sum(item["amount"] for item in plan),2)
    calc["net_pay"]=round(calc["gross_pay"]-calc["pf_deduction"]-calc["esi_deduction"]-calc["advance_recovery"]-calc["other_deductions"],2)
    for key,value in calc.items():
        if key not in ("id","employee_id","month","status","requires_review"):setattr(p,key,value)
    for item in plan:
        advance=db.session.get(Advance,item["advance_id"])
        if advance:
            advance.recovered_amount=round(float(advance.recovered_amount or 0)+item["amount"],2)
            advance.recovered_payroll_id=p.id
    p.status="Draft";p.requires_review=False
    set_audit("Payroll",p.id,"Recalculate",f"Recalculated from attendance: {p.paid_days} paid days, {p.absence_days} absent days")
    db.session.commit()
    return jsonify(item=labelled_record(p),message="Payroll recalculated from attendance and advance ledger")

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
@app.delete("/api/payroll/<pid>")
@roles("Director")
def payroll_delete(pid):
    row=db.session.get(Payroll,pid)
    if not row:return jsonify(error="Payroll record not found"),404
    try:
        # Best-effort reversal for advances whose latest recovery marker points to this payroll.
        remaining=max(0,float(row.advance_recovery or 0))
        eligible=Advance.query.filter_by(employee_id=row.employee_id,recovered_payroll_id=pid).order_by(Advance.issue_date.desc()).all()
        for advance in eligible:
            if remaining<=0:break
            cap=max(0,float(advance.monthly_recovery or advance.amount or 0))
            reverse=min(float(advance.recovered_amount or 0),cap,remaining)
            advance.recovered_amount=max(0,float(advance.recovered_amount or 0)-reverse)
            advance.recovered_payroll_id=None
            remaining-=reverse
        db.session.delete(row)
        set_audit("Payroll",pid,"Delete","Permanently deleted payroll record and reversed identifiable latest advance recoveries")
        db.session.commit()
        return jsonify(message="Payroll record deleted",deleted=True)
    except Exception as ex:
        db.session.rollback()
        return jsonify(error="Could not delete payroll record",details=str(ex)),400

@app.get("/api/advances")
@roles("Director")
def advances_list():return jsonify(items=[labelled_record(x) for x in Advance.query.all()])
@app.post("/api/advances")
@roles("Director")
def advance_create():
    d=json_body();e=db.session.get(Employee,d.get("employee_id"))
    if not e:return jsonify(error="Employee not found"),404
    amount=float(d.get("amount") or 0)
    if amount<=0:return jsonify(error="Advance must be greater than zero"),400
    monthly_recovery=float(d.get("monthly_recovery") or amount)
    if monthly_recovery<=0:return jsonify(error="Monthly recovery must be greater than zero"),400
    a=Advance(id=next_id("ADV",Advance),employee_id=e.id,issue_date=parse_date(d.get("issue_date") or now_ist_date().isoformat(),True),amount=amount,monthly_recovery=monthly_recovery,approval_status=d.get("approval_status","Pending"),recovery_month=d.get("recovery_month") or now_ist_date().strftime("%Y-%m"),notes=d.get("notes"))
    db.session.add(a);set_audit("Advance",a.id,"Create","Created advance request");db.session.commit();return jsonify(item=asdict(a)),201
@app.delete("/api/advances/<aid>")
@roles("Director")
def advance_delete(aid):
    row=db.session.get(Advance,aid)
    if not row:return jsonify(error="Advance record not found"),404
    db.session.delete(row)
    set_audit("Advance",aid,"Delete","Permanently deleted advance record")
    db.session.commit()
    return jsonify(message="Advance deleted",deleted=True)

@app.get("/api/salary-slips")
@roles("Director")
def salary_slips():return jsonify(items=[labelled_record(x) for x in Payroll.query.filter(Payroll.status.in_(["Approved","Paid"])).all()])
@app.get("/api/statutory")
@roles("Director")
def statutory():return jsonify(items=[])
@app.get("/api/verification")
@roles("Director")
def verification_list():return jsonify(items=[labelled_record(x) for x in Verification.query.all()])
@app.delete("/api/verification/<int:vid>")
@roles("Director")
def verification_delete(vid):
    row=db.session.get(Verification,vid)
    if not row:return jsonify(error="Verification record not found"),404
    db.session.delete(row)
    set_audit("Verification",vid,"Delete","Permanently deleted verification record")
    db.session.commit()
    return jsonify(message="Verification record deleted",deleted=True)

@app.post("/api/verification")
@roles("Director")
def verification_create():
    d=json_body();v=Verification(employee_id=d.get("employee_id"),aadhaar_status=d.get("aadhaar_status","Not checked"),pan_status=d.get("pan_status","Not checked"),tenth_status=d.get("tenth_status","Not checked"))
    if not db.session.get(Employee,v.employee_id):return jsonify(error="Employee not found"),404
    db.session.add(v);set_audit("Verification",v.employee_id,"Create","Updated verification status");db.session.commit();return jsonify(item=asdict(v)),201
@app.get("/api/users")
@roles("Director")
def users_list():
    items=[]
    for u in User.query.all():
        emp=db.session.get(Employee,u.employee_id) if u.employee_id else None
        site_ids=[x.strip() for x in (u.site_ids or "").split(",") if x.strip()]
        items.append({"id":u.id,"username":u.username,"display_name":u.display_name,"role":u.role,"employee_id":u.employee_id,"employee_name":emp.name if emp else "","site_ids":u.site_ids,"site_names":[site.name for sid in site_ids if (site:=db.session.get(Site,sid))],"active":u.active,"must_change_password":u.must_change_password})
    return jsonify(items=items)
@app.post("/api/users")
@roles("Director")
def users_create():
    d=json_body();username=d.get("username","").strip();pw=d.get("temporary_password","")
    if not username or len(pw)<12:return jsonify(error="Username required; temporary password must be at least 12 characters"),400
    if User.query.filter_by(username=username).first():return jsonify(error="Username already exists"),409
    role=d.get("role","Manager");sites_value=d.get("site_ids") or "";sites=[str(x).strip() for x in sites_value if str(x).strip()] if isinstance(sites_value,list) else [x.strip() for x in sites_value.split(",") if x.strip()]
    if role=="Manager" and len(sites)>int(setting("manager_site_limit",20)):return jsonify(error="Manager may have up to 20 sites"),400
    if any(not db.session.get(Site,s) for s in sites):return jsonify(error="Invalid site ID"),400
    employee_id=(d.get("employee_id") or "").strip() or None
    if role=="Manager":
        manager=db.session.get(Employee,employee_id) if employee_id else None
        if not manager or manager.designation!="Manager": return jsonify(error="Choose the existing Manager employee record"),400
        if sites and any(db.session.get(Site,s).manager_employee_id not in (None,employee_id) for s in sites): return jsonify(error="A selected site is assigned to another Manager"),400
        for sid in sites:
            site=db.session.get(Site,sid);site.manager_employee_id=employee_id
    u=User(username=username,display_name=d.get("display_name",username),role=role,employee_id=employee_id,site_ids=",".join(sites),password_hash=generate_password_hash(pw),must_change_password=True)
    db.session.add(u);db.session.flush();set_audit("User",u.id,"Create",f"Created {role} account");db.session.commit();return jsonify(item={"id":u.id,"username":u.username,"role":u.role},message="Account created; user must change password"),201

@app.put("/api/users/<int:uid>")
@roles("Director")
def users_update(uid):
    u=db.session.get(User,uid)
    if not u:return jsonify(error="User account not found"),404
    d=json_body()
    username=(d.get("username",u.username) or "").strip()
    if not username:return jsonify(error="Username is required"),400
    other=User.query.filter(User.username==username,User.id!=uid).first()
    if other:return jsonify(error="Username already exists"),409
    role=d.get("role",u.role)
    employee_id=(d.get("employee_id",u.employee_id) or "").strip() or None
    sites_value=d.get("site_ids",u.site_ids or "")
    sites=[str(x).strip() for x in sites_value if str(x).strip()] if isinstance(sites_value,list) else [x.strip() for x in (sites_value or "").split(",") if x.strip()]
    if role=="Manager":
        manager=db.session.get(Employee,employee_id) if employee_id else None
        if not manager or manager.designation!="Manager":return jsonify(error="Choose a valid Manager employee record"),400
        if len(sites)>int(setting("manager_site_limit",20)):return jsonify(error="Manager may have up to 20 sites"),400
    if any(not db.session.get(Site,sid) for sid in sites):return jsonify(error="One or more selected site IDs are invalid"),400
    if role=="Manager":
        for sid in sites:
            site=db.session.get(Site,sid)
            if site.manager_employee_id not in (None,employee_id):return jsonify(error=f"Site {site.name} is assigned to another Manager"),409
    password=d.get("temporary_password")
    if password and len(password)<12:return jsonify(error="Password must be at least 12 characters"),400
    # Release site ownership that was removed from this Manager's selection
    # or when the account is no longer a Manager.
    old_manager_employee_id=u.employee_id if u.role=="Manager" else None
    desired_sites=set(sites) if role=="Manager" and employee_id else set()
    if old_manager_employee_id:
        old_manager= db.session.get(Employee,old_manager_employee_id)
        for old_site in Site.query.filter_by(manager_employee_id=old_manager_employee_id).all():
            if old_site.id not in desired_sites:
                old_site.manager_employee_id=None
                if old_manager:
                    old_ids=[x.strip() for x in (old_manager.site_ids or "").split(",") if x.strip() and x.strip()!=old_site.id]
                    old_manager.site_ids=",".join(old_ids)
    u.username=username;u.display_name=d.get("display_name",u.display_name);u.role=role;u.employee_id=employee_id;u.site_ids=",".join(sites)
    if password:
        u.password_hash=generate_password_hash(password);u.must_change_password=True
    if "active" in d:
        active_value=d["active"]
        u.active=active_value if isinstance(active_value,bool) else str(active_value).strip().lower() in ("true","1","yes","on")
    if role=="Manager":
        new_manager=db.session.get(Employee,employee_id)
        for sid in sites:
            assigned_site=db.session.get(Site,sid)
            assigned_site.manager_employee_id=employee_id
            if new_manager:
                new_ids=[x.strip() for x in (new_manager.site_ids or "").split(",") if x.strip()]
                if sid not in new_ids:new_ids.append(sid)
                new_manager.site_ids=",".join(new_ids)
    set_audit("User",uid,"Update","Updated user account and optional password")
    db.session.commit()
    return jsonify(item={"id":u.id,"username":u.username,"display_name":u.display_name,"role":u.role,"employee_id":u.employee_id,"site_ids":u.site_ids,"active":u.active,"must_change_password":u.must_change_password},message="User updated"+("; password changed and must be changed at next login" if password else ""))

@app.delete("/api/users/<int:uid>")
@roles("Director")
def users_delete(uid):
    u=db.session.get(User,uid)
    if not u:return jsonify(error="User account not found"),404
    if u.id==g.user.id:return jsonify(error="You cannot delete your own signed-in account"),409
    db.session.delete(u)
    set_audit("User",uid,"Delete","Permanently deleted user account")
    db.session.commit()
    return jsonify(message="User account permanently deleted",deleted=True)

@app.get("/api/lookups")
@token_required
def lookups():
    allowed=site_ids_for_user()
    employees=Employee.query.filter_by(status="Active").all()
    sites=Site.query.filter_by(status="Active").all()
    managers=Employee.query.filter_by(designation="Manager",status="Active").all() if g.user.role=="Director" else []
    if g.user.role=="Manager":
        sites=[s for s in sites if s.manager_employee_id==g.user.employee_id]
        allowed_manager_sites={s.id for s in sites}
        employees=[e for e in employees if e.designation in ("Security Guard","Supervisor") and e.manager_employee_id==g.user.employee_id and bool({x.strip() for x in (e.site_ids or "").split(",") if x.strip()} & allowed_manager_sites)]
    elif allowed is not None:
        employees=[e for e in employees if set((e.site_ids or "").split(","))&allowed]
        sites=[s for s in sites if s.id in allowed]
    return jsonify(employees=[{"id":e.id,"name":e.name,"designation":e.designation,"manager_employee_id":e.manager_employee_id,"site_ids":[x.strip() for x in (e.site_ids or "").split(",") if x.strip()]} for e in employees], managers=[{"id":e.id,"name":e.name} for e in managers], sites=[{"id":s.id,"name":s.name,"manager_employee_id":s.manager_employee_id} for s in sites])

@app.get("/api/employees/<eid>/profile")
@roles("Director")
def employee_profile(eid):
    e=db.session.get(Employee,eid)
    if not e:return jsonify(error="Employee not found"),404
    attendance=Attendance.query.filter_by(employee_id=eid).order_by(Attendance.date.desc()).all()
    payroll=Payroll.query.filter_by(employee_id=eid).order_by(Payroll.month.desc()).all()
    advances=Advance.query.filter_by(employee_id=eid).order_by(Advance.issue_date.desc()).all()
    return jsonify(employee=employee_payload(e),attendance=[labelled_record(a) for a in attendance],payroll=[labelled_record(p) for p in payroll],advances=[labelled_record(a) for a in advances])

@app.get("/api/audit")
@roles("Director")
def audit_list():return jsonify(items=[asdict(x) for x in Audit.query.order_by(Audit.id.desc()).limit(500).all()])
@app.get("/api/reports/attendance")
@token_required
def attendance_report():
    month=request.args.get("month",now_ist_date().strftime("%Y-%m"));allowed=site_ids_for_user()
    rows=Attendance.query.all()
    rows=[x for x in rows if x.date.strftime("%Y-%m")==month and (allowed is None or x.site_id in allowed)]
    return jsonify(items=[labelled_record(x) for x in rows])
@app.get("/api/settings")
@roles("Director")
def settings_get():return jsonify(settings={k:(0 if k=="absence_grace_days" else setting(k,v)) for k,v in {"salary_divisor":30,"absence_grace_days":0,"manager_site_limit":20,"director_salary":45000,"bonus_cut_two_absences":800,"ot_rate":0,"wo_ot_rate":0,"pf_rate":0,"esi_rate":0}.items()})
@app.put("/api/settings")
@roles("Director")
def settings_put():
    d=json_body()
    allowed={"salary_divisor","manager_site_limit","director_salary","bonus_cut_two_absences","ot_rate","wo_ot_rate","pf_rate","esi_rate"}
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
    defaults={"salary_divisor":"30","absence_grace_days":"0","manager_site_limit":"20","director_salary":"45000","bonus_cut_two_absences":"800","ot_rate":"0","wo_ot_rate":"0","pf_rate":"0","esi_rate":"0"}
    for k,v in defaults.items():
        if not db.session.get(Setting,k):db.session.add(Setting(key=k,value=v))
    username=os.getenv("BOOTSTRAP_ADMIN_USERNAME","admin");password=os.getenv("BOOTSTRAP_ADMIN_PASSWORD","")
    if password and not User.query.filter_by(username=username).first():
        db.session.add(User(username=username,display_name="SVSA Director",role="Director",password_hash=generate_password_hash(password),must_change_password=True))
    db.session.commit()
with app.app_context():
    seed()
    migrate_additive_columns()
    # Migrate the previous two-absence grace default to the new 0-day policy once.
    grace_setting=db.session.get(Setting,"absence_grace_days")
    if grace_setting and grace_setting.value=="2":
        grace_setting.value="0"
        db.session.commit()
if __name__=="__main__":app.run(host="0.0.0.0",port=int(os.getenv("PORT",5000)),debug=False)
