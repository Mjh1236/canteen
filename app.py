import json, os, math, socket, uuid
from datetime import datetime
from functools import wraps
from flask import Flask, request, jsonify, render_template_string, redirect, url_for, make_response
from flask_cors import CORS
import jwt
from werkzeug.security import generate_password_hash, check_password_hash

# 修复中文Windows下socket.getfqdn编码问题
_orig_getfqdn = socket.getfqdn
socket.getfqdn = lambda name='': (_orig_getfqdn(name) if False else 'localhost')

app = Flask(__name__)
CORS(app)
app.config['SECRET_KEY'] = 'canteen_jwt_secret_2024'

# ==================== Supabase 数据库 ====================
SUPABASE_URL = os.environ.get('SUPABASE_URL', 'https://ddgiwuhhdirzjsralvxd.supabase.co')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY', 'sb_publishable_fUQWTpb8q46nfSLl8GU1pQ_R2G2bCsf')
SUPABASE_SERVICE_KEY = os.environ.get('SUPABASE_SERVICE_KEY', '')
_STATE_URL = f'{SUPABASE_URL}/rest/v1/state?id=eq.1'
_HEADERS = {'apikey': SUPABASE_KEY, 'Authorization': f'Bearer {SUPABASE_KEY}',
            'Content-Type': 'application/json', 'Prefer': 'return=representation'}

import urllib.request as _ur

def _empty_db():
    return {'users':[], 'canteens':[], 'dishes':[], 'reviews':[], 'favorites':[],
            'seq':{'user':0,'canteen':0,'dish':0,'review':0,'favorite':0}}

def load_db():
    # 本地缓存始终是第一优先级，增删改立即生效且不会被云端覆盖
    local = _local_load()
    if local.get('canteens') or local.get('users'):
        return local
    # 本地无缓存（首次启动或文件丢失），从Supabase加载
    try:
        req = _ur.Request(_STATE_URL, headers={k:v for k,v in _HEADERS.items() if k!='Content-Type'})
        resp = _ur.urlopen(req, timeout=10)
        rows = json.loads(resp.read())
        if rows and 'data' in rows[0]:
            data = rows[0]['data']
            if data.get('canteens') or data.get('users'):
                _local_save(data)
                return data
    except Exception:
        pass
    return _empty_db()

def save_db(db):
    # 本地缓存始终先保存
    _local_save(db)
    # 同步到Supabase云端（重试3次确保写入成功）
    if SUPABASE_SERVICE_KEY:
        headers = dict(_HEADERS)
        headers['apikey'] = SUPABASE_SERVICE_KEY
        headers['Authorization'] = f'Bearer {SUPABASE_SERVICE_KEY}'
        body = json.dumps({'data': db}, ensure_ascii=False).encode('utf-8')
        for attempt in range(3):
            try:
                req = _ur.Request(_STATE_URL, data=body, method='PATCH', headers=headers)
                resp = _ur.urlopen(req, timeout=10)
                if resp.getcode() in (200, 201, 204):
                    break  # 成功
                print(f'Supabase异常({attempt+1}/3): {resp.getcode()}')
            except Exception as e:
                print(f'Supabase失败({attempt+1}/3): {e}')

# 本地缓存（Supabase故障时的备份）
import sys as _sys, tempfile as _tmp
if getattr(_sys, 'frozen', False):
    _BASE_DIR = os.path.dirname(_sys.executable)
else:
    _BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_CACHE_FILE = os.path.join(_BASE_DIR, 'data', 'cache.json')
os.makedirs(os.path.dirname(_CACHE_FILE), exist_ok=True)

# 图片上传目录
UPLOAD_FOLDER = os.path.join(_BASE_DIR, 'static', 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def _local_load():
    if os.path.exists(_CACHE_FILE):
        with open(_CACHE_FILE,'r',encoding='utf-8') as f: return json.load(f)
    return {'users':[], 'canteens':[], 'dishes':[], 'reviews':[], 'favorites':[],
            'seq':{'user':0,'canteen':0,'dish':0,'review':0,'favorite':0}}

def _local_save(db):
    with open(_CACHE_FILE,'w',encoding='utf-8') as f: json.dump(db,f,ensure_ascii=False,indent=2)

def nid(db,key):
    db['seq'][key]=db['seq'].get(key,0)+1
    return db['seq'][key]

# ==================== 种子数据 ====================
def seed():
    db = load_db()
    if db['canteens'] and db['dishes'] and db['users']: return
    # 数据不完整时补充缺失数据
    if not db['canteens']:
        c = nid(db,'canteen')
        db['canteens']=[{'id':c,'name':'第三食堂','campus':'主校区','floor':1,'open_time':'06:30','close_time':'21:30','desc':'主校区核心食堂，菜品丰富多样，环境整洁舒适'}]
    canteen_id = db['canteens'][0]['id'] if db['canteens'] else nid(db,'canteen')
    if not db['dishes']:
        raw=[('宫保鸡丁盖饭','盖饭',14,'鸡肉鲜嫩，花生酥脆'),('鱼香肉丝盖饭','盖饭',13,'酸甜可口，下饭神器'),('红烧排骨面','面食',16,'排骨软烂入味，汤头浓郁'),('番茄鸡蛋面','面食',10,'经典搭配，营养均衡'),('麻辣香锅','小炒',22,'自选食材，麻辣鲜香'),('糖醋里脊','小炒',18,'外酥里嫩，酸甜适口'),('蛋炒饭','主食',8,'粒粒分明，简单美味'),('酸辣粉','小吃',9,'酸辣开胃，粉条爽滑'),('兰州拉面','面食',12,'手工拉制，汤清味浓'),('黄焖鸡米饭','盖饭',16,'鸡肉鲜嫩多汁'),('麻辣烫','小吃',15,'自选菜品，麻辣过瘾'),('铁板牛肉饭','盖饭',20,'铁板现做，香气四溢'),('馄饨','小吃',8,'皮薄馅大，汤鲜味美'),('炒河粉','主食',11,'Q弹爽滑，锅气十足'),('手抓饼','小吃',7,'外酥里软，方便快捷'),('水煮肉片','小炒',25,'麻辣鲜嫩，分量十足'),('清蒸鲈鱼','小炒',28,'肉质细嫩，鲜美无比'),('干煸四季豆','小炒',15,'干香微辣，下饭好菜'),('酸菜鱼','小炒',26,'酸辣鲜香，鱼肉嫩滑'),('回锅肉盖饭','盖饭',17,'肥而不腻，酱香浓郁')]
        db['dishes']=[]
        for nm,cat,pr,de in raw:
            d=nid(db,'dish')
            db['dishes'].append({'id':d,'canteen_id':canteen_id,'name':nm,'category':cat,'price':pr,'desc':de,'image':'','avg_rating':0,'review_count':0,'is_available':True,'created_at':datetime.now().isoformat()})
    if not db['users']:
        a=nid(db,'user')
        db['users'].append({'id':a,'student_id':'admin','nickname':'系统管理员','password':generate_password_hash('admin123'),'role':'admin','created_at':datetime.now().isoformat()})
        u=nid(db,'user')
        db['users'].append({'id':u,'student_id':'2024001','nickname':'美食探索者','password':generate_password_hash('123456'),'role':'user','created_at':datetime.now().isoformat()})
    save_db(db)
seed()

# ==================== 认证 ====================
def login_required(f):
    @wraps(f)
    def d(*a,**kw):
        token=request.cookies.get('token') or request.headers.get('Authorization','').replace('Bearer ','')
        if not token: return redirect('/login')
        try: request.user=jwt.decode(token,app.config['SECRET_KEY'],algorithms=['HS256'])
        except: return redirect('/login')
        return f(*a,**kw)
    return d

def admin_only(f):
    @wraps(f)
    def d(*a,**kw):
        db=load_db()
        u=next((x for x in db['users'] if x['id']==request.user['id']),None)
        if not u or u['role']!='admin': return '<script>alert("需要管理员权限");history.back()</script>'
        return f(*a,**kw)
    return d

def current_user():
    token=request.cookies.get('token','')
    if not token: return None
    try: return jwt.decode(token,app.config['SECRET_KEY'],algorithms=['HS256'])
    except: return None

# ==================== 页面框架 ====================
CSS = '''
*{margin:0;padding:0;box-sizing:border-box}
:root{--p:#FF6B35;--pl:#FFA726;--bg:#f5f5f5;--w:#fff;--t:#333;--tl:#999;--b:#eee;--s:0 2px 12px rgba(0,0,0,.08);--r:12px}
body{font-family:'PingFang SC','Microsoft YaHei',sans-serif;background:var(--bg);color:var(--t);min-height:100vh}
.navbar{background:linear-gradient(135deg,var(--p),var(--pl));color:var(--w);padding:0 20px;display:flex;align-items:center;justify-content:space-between;height:56px;position:sticky;top:0;z-index:100;box-shadow:0 2px 8px rgba(255,107,53,.3)}
.navbar a{color:var(--w);text-decoration:none;font-size:14px;padding:6px 12px;border-radius:6px}
.navbar a:hover{background:rgba(255,255,255,.2)}
.navbar .logo{font-size:18px;font-weight:700}
.container{max-width:1100px;margin:0 auto;padding:20px}
.card{background:var(--w);border-radius:var(--r);padding:20px;box-shadow:var(--s);margin-bottom:16px}
.card-hd{font-size:18px;font-weight:700;margin-bottom:16px;padding-bottom:12px;border-bottom:2px solid var(--p);color:var(--p)}
.dish-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:16px}
.dish-card{background:var(--w);border-radius:var(--r);padding:16px;box-shadow:var(--s);transition:transform .2s}
.dish-card:hover{transform:translateY(-3px)}
.dish-card h3{font-size:16px;margin-bottom:4px}
.dish-card .cat{display:inline-block;background:#FFF3E0;color:var(--p);padding:2px 10px;border-radius:12px;font-size:12px;margin-bottom:8px}
.dish-card .price{color:#E53935;font-size:18px;font-weight:700}
.dish-card .meta{font-size:13px;color:var(--tl);margin-top:6px}
.stars{color:#FFB800;font-size:16px;letter-spacing:2px}
.stars .empty{color:#ddd}
.stars.big{font-size:26px}
.stars .s{cursor:pointer;transition:transform .2s}
.stars .s:hover{transform:scale(1.3)}
.btn{padding:10px 24px;border:none;border-radius:8px;cursor:pointer;font-size:14px;font-weight:600;display:inline-block;text-decoration:none}
.btn-p{background:var(--p);color:var(--w)}
.btn-p:hover{opacity:.85}
.btn-o{background:transparent;border:1px solid var(--w);color:var(--w);padding:6px 14px;border-radius:20px;cursor:pointer;font-size:13px}
.btn-o:hover{background:var(--w);color:var(--p)}
.btn-sm{padding:6px 12px;border-radius:6px;border:1px solid var(--p);font-size:12px;cursor:pointer;background:transparent;color:var(--p)}
.btn-sm:hover,.btn-sm.on{background:var(--p);color:var(--w)}
.btn-danger{background:#E53935;color:var(--w)}
.btn-block{display:block;width:100%;text-align:center}
.fg{margin-bottom:16px}
.fg label{display:block;margin-bottom:6px;font-weight:600;font-size:14px}
.fg input,.fg textarea,.fg select{width:100%;padding:10px 14px;border:1px solid var(--b);border-radius:8px;font-size:14px;outline:none}
.fg input:focus,.fg textarea:focus,.fg select:focus{border-color:var(--p)}
.fg textarea{resize:vertical;min-height:80px}
.tabs{display:flex;border-bottom:2px solid var(--b);margin-bottom:20px}
.tab{padding:10px 24px;cursor:pointer;font-size:14px;font-weight:600;color:var(--tl);border-bottom:2px solid transparent;margin-bottom:-2px;text-decoration:none}
.tab.active{color:var(--p);border-bottom-color:var(--p)}
.review-item{padding:14px 0;border-bottom:1px solid var(--b)}
.review-item:last-child{border-bottom:none}
.review-item .rh{display:flex;justify-content:space-between;align-items:center;margin-bottom:6px}
.review-item .ru{font-weight:600;font-size:14px}
.review-item .rt{font-size:12px;color:var(--tl)}
.review-item .rc{margin:8px 0;font-size:14px;line-height:1.6}
.table{width:100%;border-collapse:collapse;font-size:14px}
.table th,.table td{padding:10px 12px;text-align:left;border-bottom:1px solid var(--b)}
.table th{background:#FFF3E0;color:var(--p);font-weight:600}
.stat-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:16px}
.stat-card{background:var(--w);border-radius:var(--r);padding:20px;box-shadow:var(--s);text-align:center}
.stat-card .sv{font-size:32px;font-weight:700;color:var(--p)}
.stat-card .sl{font-size:13px;color:var(--tl);margin-top:4px}
.empty{text-align:center;padding:40px;color:var(--tl)}
.review-img{max-width:200px;max-height:200px;border-radius:8px;cursor:pointer;margin-top:8px;object-fit:cover;border:1px solid var(--b)}
.review-img:hover{opacity:.85}
.diary-entry{display:flex;gap:16px;margin-bottom:16px;padding-bottom:16px;border-bottom:1px solid var(--b)}
.diary-date{min-width:75px;text-align:center}
.diary-date .day{font-size:30px;font-weight:700;color:var(--p);line-height:1}
.diary-date .month{font-size:12px;color:var(--tl)}
.diary-content{flex:1}
.diary-content .dish-link{font-weight:700;font-size:15px;color:var(--t);text-decoration:none}
.diary-content .dish-link:hover{color:var(--p)}
.diary-img{max-width:280px;max-height:220px;border-radius:8px;object-fit:cover;cursor:pointer;margin-top:8px;display:block}
.diary-img:hover{opacity:.85}
.photo-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:16px}
.photo-card{background:var(--w);border-radius:var(--r);overflow:hidden;box-shadow:var(--s);transition:transform .2s;cursor:pointer}
.photo-card:hover{transform:translateY(-3px)}
.photo-card img{width:100%;height:200px;object-fit:cover;display:block}
.photo-card .photo-info{padding:12px}
.photo-card .photo-dish{font-weight:700;font-size:14px;margin-bottom:4px}
.photo-card .photo-meta{font-size:12px;color:var(--tl);display:flex;justify-content:space-between;align-items:center}
.photo-card .photo-text{font-size:13px;color:var(--t);margin-top:6px;line-height:1.5;overflow:hidden;text-overflow:ellipsis;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical}
.file-upload{display:flex;align-items:center;gap:8px;margin-top:6px}
.file-upload .upload-btn{padding:6px 14px;border:1px dashed var(--p);border-radius:6px;color:var(--p);font-size:13px;cursor:pointer;display:inline-block}
.file-upload .upload-btn:hover{background:#FFF3E0}
.file-upload input[type=file]{display:none}
.file-upload .file-name{font-size:12px;color:var(--tl)}
.modal-overlay{display:none;position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,.88);z-index:500;align-items:center;justify-content:center}
.modal-overlay img{max-width:92vw;max-height:92vh;border-radius:8px;object-fit:contain}
.modal-overlay.show{display:flex}
.toast{position:fixed;top:20px;right:20px;padding:12px 20px;border-radius:8px;color:var(--w);z-index:300;font-size:14px;display:none}
.toast-ok{background:#4CAF50}
.toast-err{background:#E53935}
.search-bar{display:flex;gap:10px;margin-bottom:20px;flex-wrap:wrap}
.search-bar input,.search-bar select{padding:10px 14px;border:1px solid var(--b);border-radius:8px;font-size:14px;outline:none}
.search-bar input{flex:1;min-width:180px}
.search-bar select{min-width:100px}
.chart-box{width:100%;height:350px;margin:16px 0}
@media(max-width:768px){.dish-grid{grid-template-columns:repeat(auto-fill,minmax(150px,1fr))}.search-bar{flex-direction:column}.stat-grid{grid-template-columns:repeat(2,1fr)}}
'''

PAGE = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{{ title }}</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js" defer></script>
<style>{{ css }}</style>
</head>
<body>
<nav class="navbar">
  <a href="/" class="logo">🍽️ 校园美食点评</a>
  <div>
    <a href="/">首页</a>
    <a href="/recommend">推荐</a>
    <a href="/discover">📸 发现</a>
    <a href="/diary">📔 日记</a>
    {% if user and user.role=='admin' %}<a href="/admin">管理</a>{% endif %}
  </div>
  <div>
    {% if user %}
    <span style="font-size:13px">👤 {{ user.nickname }}</span>
    <a href="/profile" style="margin-left:8px">我的</a>
    <a href="/logout" style="margin-left:4px">退出</a>
    {% else %}
    <a href="/login" class="btn-o" style="color:#fff;text-decoration:none">登录</a>
    {% endif %}
  </div>
</nav>
<div id="toast" class="toast"></div>
<div id="imgModal" class="modal-overlay" onclick="closeImg()"><img id="modalImg" src="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7" onclick="event.stopPropagation()"></div>
<div class="container">{{ content|safe }}</div>
<script>
function toast(msg,ok){var t=document.getElementById('toast');t.className='toast toast-'+(ok?'ok':'err');t.textContent=msg;t.style.display='block';setTimeout(function(){t.style.display='none'},2500)}
function starHover(r){var ss=document.querySelectorAll('.star-input .s');for(var i=0;i<5;i++)ss[i].style.color=i<r?'#FFB800':'#ddd';var h=['','很差','较差','一般','不错','超赞'];document.getElementById('starHint').textContent=h[r]}
function starOut(){var cur=parseInt(document.getElementById('starVal').value)||0;var ss=document.querySelectorAll('.star-input .s');for(var i=0;i<5;i++)ss[i].style.color=i<cur?'#FFB800':'#ddd';document.getElementById('starHint').textContent=''}
function starClick(r){document.getElementById('starVal').value=r;starOut()}
function confirmDelete(msg){return confirm(msg)}
function openImg(src){var m=document.getElementById('imgModal');document.getElementById('modalImg').src=src;m.classList.add('show')}
function closeImg(){document.getElementById('imgModal').classList.remove('show')}
function showFileName(input){var fn=input.files[0]?input.files[0].name:'未选择文件';input.parentElement.querySelector('.file-name').textContent=fn}
</script>
</body>
</html>'''

def render(title, content, user=None):
    return render_template_string(PAGE, title=title, css=CSS, content=content, user=user)

def stars_html(rating, interactive=False):
    if interactive:
        h='<span class="stars big star-input">'
        for i in range(1,6): h+=f'<span class="s" style="color:#ddd" onmouseover="starHover({i})" onmouseout="starOut()" onclick="starClick({i})">★</span>'
        h+='</span><span id="starHint" style="margin-left:8px;color:var(--tl)"></span><input type="hidden" id="starVal" name="rating" value="0">'
        return h
    h='<span class="stars">'
    for i in range(1,6): h+=f'<span class="{"s" if i<=rating else "empty"}">★</span>' if interactive else f'<span>{"★" if i<=rating else "☆"}</span>'
    h+='</span>'
    if not interactive: h+=f' <small style="color:var(--tl)">{rating}分</small>'
    return h

def dish_card(d):
    return f'''<div class="dish-card">
    <a href="/dish/{d['id']}" style="text-decoration:none;color:inherit">
    <h3>{d['name']}</h3>
    <span class="cat">{d['category']}</span>
    <div class="price">¥{d['price']}</div>
    <div class="meta">{stars_html(d['avg_rating'])} {d['review_count']}条评价</div>
    </a>
    <div style="margin-top:8px">
    <form method="post" action="/fav/{d['id']}" style="display:inline">
    <button class="btn-sm">⭐ 收藏</button></form>
    </div></div>'''

def category_tags(current=''):
    db=load_db()
    cats=sorted(set(d['category'] for d in db['dishes']))
    h=''
    for c in cats:
        cls='tab active' if c==current else 'tab'
        h+=f'<a href="/?category={c}" class="{cls}">{c}</a>'
    return h

# ==================== 页面路由 ====================

@app.route('/')
def home():
    db=load_db()
    u=current_user(); user=None
    if u:
        user=next((x for x in db['users'] if x['id']==u['id']),None)
    kw=request.args.get('keyword','')
    cat=request.args.get('category','')
    sort=request.args.get('sort','')
    dishes=[d for d in db['dishes']]
    if kw: dishes=[d for d in dishes if kw in d['name'] or kw in d['desc']]
    if cat: dishes=[d for d in dishes if d['category']==cat]
    if sort=='rating': dishes.sort(key=lambda d:d['avg_rating'],reverse=True)
    elif sort=='price': dishes.sort(key=lambda d:d['price'])
    elif sort=='popular': dishes.sort(key=lambda d:d['review_count'],reverse=True)
    else: dishes.sort(key=lambda d:d['id'],reverse=True)

    hot=sorted([d for d in db['dishes']],key=lambda d:d['avg_rating']*math.log(d['review_count']+2),reverse=True)[:8]

    canteens=[]
    for c in db['canteens']:
        c=dict(c)
        c['dishCount']=len([d for d in db['dishes'] if d['canteen_id']==c['id']])
        canteens.append(c)

    cats=sorted(set(d['category'] for d in db['dishes']))

    content=f'''
    <form class="search-bar" method="get" action="/">
      <input type="text" name="keyword" placeholder="🔍 搜索菜品..." value="{kw}">
      <select name="category"><option value="">全部分类</option>{"".join(f'<option value="{c}" {"selected" if c==cat else ""}>{c}</option>' for c in cats)}</select>
      <select name="sort"><option value="">默认排序</option><option value="rating" {"selected" if sort=="rating" else ""}>评分最高</option><option value="price" {"selected" if sort=="price" else ""}>价格最低</option><option value="popular" {"selected" if sort=="popular" else ""}>评价最多</option></select>
      <button class="btn btn-p" type="submit">搜索</button>
    </form>
    <div class="card"><div class="card-hd">🏫 食堂导航</div>
      <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:16px">
      {"".join(f'<a href="/canteen/{c["id"]}" style="text-decoration:none;color:inherit"><div class="card" style="cursor:pointer"><h3 style="color:var(--p)">{c["name"]}</h3><p style="font-size:14px;color:var(--tl)">{c["campus"]} {c["floor"]}楼</p><p style="font-size:13px;color:var(--tl)">⏰ {c["open_time"]}-{c["close_time"]} | 📋 {c["dishCount"]}道菜品</p></div></a>' for c in canteens)}
      </div></div>
    <div class="card"><div class="card-hd">🔥 热门推荐</div>
      <div class="dish-grid">{"".join(dish_card(d) for d in hot)}</div></div>
    <div class="card"><div class="card-hd">{'🔍 搜索结果' if kw else '📋 全部菜品'} ({len(dishes)})</div>
      <div style="margin-bottom:16px"><a href="/" class="tab">全部</a>{"".join(f'<a href="/?category={c}" class="tab{" active" if c==cat else ""}">{c}</a>' for c in cats)}</div>
      <div class="dish-grid">{"".join(dish_card(d) for d in dishes[:20])}</div>
    </div>'''
    return render('校园食堂菜品评价与就餐推荐系统', content, user)

@app.route('/login', methods=['GET','POST'])
def login_page():
    error=''
    if request.method=='POST':
        sid=request.form.get('student_id','').strip()
        pw=request.form.get('password','').strip()
        db=load_db()
        user=next((u for u in db['users'] if u['student_id']==sid),None)
        if user and check_password_hash(user['password'],pw):
            token=jwt.encode({'id':user['id'],'role':user['role']},app.config['SECRET_KEY'],algorithm='HS256')
            resp=make_response(redirect('/', code=303))
            resp.set_cookie('token',token,max_age=7*86400)
            return resp
        error='学号或密码错误'
    content=f'''
    <div class="card" style="max-width:420px;margin:40px auto">
    <div class="card-hd">🔑 登录</div>
    {'<p style="color:#E53935;margin-bottom:12px">'+error+'</p>' if error else ''}
    <form method="post" action="/login">
    <div class="fg"><label>学号/工号</label><input name="student_id" placeholder="请输入学号" required></div>
    <div class="fg"><label>密码</label><input name="password" type="password" placeholder="请输入密码" required></div>
    <button class="btn btn-p btn-block" type="submit">登录</button>
    </form>
    <p style="margin-top:16px;text-align:center">还没有账号？<a href="/register" style="color:var(--p)">立即注册</a></p>
    <p style="margin-top:8px;font-size:12px;color:var(--tl);text-align:center">提示：管理员 admin / admin123</p>
    </div>'''
    return render('登录', content)

@app.route('/register', methods=['GET','POST'])
def register_page():
    error=''
    if request.method=='POST':
        sid=request.form.get('student_id','').strip()
        nick=request.form.get('nickname','').strip()
        pw=request.form.get('password','').strip()
        if not all([sid,nick,pw]): error='请填写完整信息'
        else:
            db=load_db()
            if any(u['student_id']==sid for u in db['users']): error='该学号已注册'
            else:
                user={'id':nid(db,'user'),'student_id':sid,'nickname':nick,'password':generate_password_hash(pw),'role':'user','created_at':datetime.now().isoformat()}
                db['users'].append(user); save_db(db)
                token=jwt.encode({'id':user['id'],'role':user['role']},app.config['SECRET_KEY'],algorithm='HS256')
                resp=make_response(redirect('/', code=303))
                resp.set_cookie('token',token,max_age=7*86400)
                return resp
    content=f'''
    <div class="card" style="max-width:420px;margin:40px auto">
    <div class="card-hd">📝 注册</div>
    {'<p style="color:#E53935;margin-bottom:12px">'+error+'</p>' if error else ''}
    <form method="post" action="/register">
    <div class="fg"><label>学号/工号</label><input name="student_id" placeholder="请输入学号" required></div>
    <div class="fg"><label>昵称</label><input name="nickname" placeholder="请输入昵称" required></div>
    <div class="fg"><label>密码</label><input name="password" type="password" placeholder="请设置密码" required></div>
    <button class="btn btn-p btn-block" type="submit">注册</button>
    </form>
    <p style="margin-top:16px;text-align:center">已有账号？<a href="/login" style="color:var(--p)">去登录</a></p>
    </div>'''
    return render('注册', content)

@app.route('/logout')
def logout():
    resp=make_response(redirect('/'))
    resp.delete_cookie('token')
    return resp

@app.route('/canteen/<int:id>')
def canteen_page(id):
    db=load_db()
    u=current_user(); user=None
    if u: user=next((x for x in db['users'] if x['id']==u['id']),None)
    c=next((x for x in db['canteens'] if x['id']==id),None)
    if not c: return render('404', '<div class="empty"><h2>食堂不存在</h2></div>')
    dishes=[d for d in db['dishes'] if d['canteen_id']==id]
    content=f'''
    <div class="card"><h2>{c['name']}</h2>
      <p style="color:var(--tl)">📍 {c['campus']} {c['floor']}楼 | ⏰ {c['open_time']}-{c['close_time']}</p>
      <p style="margin-top:8px">{c['desc']}</p></div>
    <div class="card"><div class="card-hd">📋 菜品列表 ({len(dishes)})</div>
      <div class="dish-grid">{"".join(dish_card(d) for d in dishes) or '<div class="empty">暂无菜品</div>'}</div></div>'''
    return render(c['name'], content, user)

@app.route('/dish/<int:id>', methods=['GET','POST'])
def dish_page(id):
    db=load_db()
    u=current_user(); user=None
    if u: user=next((x for x in db['users'] if x['id']==u['id']),None)
    dish=next((d for d in db['dishes'] if d['id']==id),None)
    if not dish: return render('404','<div class="empty"><h2>菜品不存在</h2></div>')
    canteen=next((c for c in db['canteens'] if c['id']==dish['canteen_id']),None)

    # 提交评价
    if request.method=='POST' and user:
        rating=int(request.form.get('rating',0))
        content_text=request.form.get('content','').strip()
        image_filename=''
        file=request.files.get('image')
        if file and file.filename and allowed_file(file.filename):
            ext=file.filename.rsplit('.',1)[1].lower()
            image_filename=f"{uuid.uuid4().hex}.{ext}"
            file.save(os.path.join(UPLOAD_FOLDER, image_filename))
        if rating>=1 and rating<=5:
            review={'id':nid(db,'review'),'user_id':user['id'],'dish_id':id,'rating':rating,'content':content_text,'image':image_filename,'likes':0,'created_at':datetime.now().isoformat()}
            db['reviews'].append(review)
            all_r=[r for r in db['reviews'] if r['dish_id']==id]
            dish['avg_rating']=round(sum(r['rating'] for r in all_r)/len(all_r),1)
            dish['review_count']=len(all_r)
            save_db(db)
            return redirect(f'/dish/{id}')

    reviews=sorted([r for r in db['reviews'] if r['dish_id']==id],key=lambda r:r['id'],reverse=True)
    reviews_html=''
    for r in reviews:
        ru=next((u for u in db['users'] if u['id']==r['user_id']),None)
        del_btn=''
        if user and (user['id']==r['user_id'] or user['role']=='admin'):
            del_btn=f'<form method="post" action="/review/{r["id"]}/delete" style="display:inline" onsubmit="return confirm(\'确定删除？\')"><button class="btn-sm" style="border-color:#E53935;color:#E53935">删除</button></form>'
        img_html=''
        if r.get('image'):
            img_html=f'<img src="/static/uploads/{r["image"]}" class="review-img" onclick="openImg(this.src)" alt="菜品实拍">'
        reviews_html+=f'''<div class="review-item">
        <div class="rh"><span class="ru">{ru["nickname"] if ru else "匿名"}</span><span class="rt">{r["created_at"][:16].replace("T"," ")}</span></div>
        <div>{stars_html(r["rating"])}</div>
        <div class="rc">{r["content"]}{img_html}</div>
        <a href="/review/{r["id"]}/like" style="font-size:12px;color:var(--tl);text-decoration:none">👍 {r["likes"]} 有用</a>
        {del_btn}</div>'''

    review_form=''
    if user:
        review_form=f'''
        <div style="background:#FFF8E1;padding:16px;border-radius:8px;margin-bottom:16px">
        <form method="post" enctype="multipart/form-data">
        <div style="font-weight:600;margin-bottom:8px">发表评价</div>
        <div style="margin-bottom:8px">{stars_html(0,interactive=True)}</div>
        <textarea name="content" placeholder="分享你的用餐体验..." style="width:100%;padding:10px;border:1px solid var(--b);border-radius:8px;min-height:60px;font-size:14px"></textarea>
        <div class="file-upload">
          <label class="upload-btn" for="reviewImage">📷 晒图打卡</label>
          <input type="file" id="reviewImage" name="image" accept="image/*" onchange="showFileName(this)">
          <span class="file-name">未选择图片</span>
        </div>
        <button class="btn btn-p" style="margin-top:8px" type="submit">提交评价</button>
        </form></div>'''
    else:
        review_form='<p style="text-align:center;padding:16px;color:var(--tl)">请<a href="/login" style="color:var(--p)">登录</a>后发表评价</p>'

    content=f'''
    <div class="card">
      <div style="display:flex;gap:20px;flex-wrap:wrap">
        <div style="flex:1;min-width:280px">
          <span class="cat">{dish["category"]}</span>
          <h2 style="margin:8px 0">{dish["name"]}</h2>
          <p style="color:var(--tl)">📍 {canteen["name"] if canteen else "未知食堂"}</p>
          <div style="font-size:28px;color:#E53935;font-weight:700;margin:12px 0">¥{dish["price"]}</div>
          <div style="font-size:16px;margin:8px 0">{stars_html(dish["avg_rating"])} {dish["avg_rating"]}分 · {dish["review_count"]}条评价</div>
          <p style="color:var(--tl)">{dish["desc"]}</p>
          <form method="post" action="/fav/{dish["id"]}" style="margin-top:16px">
          <button class="btn btn-p">⭐ 收藏</button></form>
        </div></div></div>
    <div class="card"><div class="card-hd">💬 用户评价 ({len(reviews)})</div>
      {review_form}{reviews_html or '<div class="empty">暂无评价，成为第一个评价的人吧！</div>'}</div>'''
    return render(dish['name'], content, user)

@app.route('/recommend')
def recommend_page():
    db=load_db()
    u=current_user(); user=None
    if u: user=next((x for x in db['users'] if x['id']==u['id']),None)
    hot=sorted([d for d in db['dishes'] if d['is_available']],key=lambda d:d['avg_rating']*math.log(d['review_count']+2),reverse=True)[:8]

    personal_html=''
    if user:
        my_r=[r for r in db['reviews'] if r['user_id']==user['id']]
        rated=set(r['dish_id'] for r in my_r)
        high=[r for r in my_r if r['rating']>=4]
        if high:
            fav_cats=list(set(next((d['category'] for d in db['dishes'] if d['id']==r['dish_id']),None) for r in high))
            fav_cats=[c for c in fav_cats if c]
            pdishes=[d for d in db['dishes'] if d['is_available'] and d['id'] not in rated and d['category'] in fav_cats]
            pdishes.sort(key=lambda d:d['avg_rating'],reverse=True)
            personal_html=f'<div class="card"><div class="card-hd">🎯 个性化推荐 <small style="font-weight:400;color:var(--tl)">偏好：{"、".join(fav_cats)}</small></div><div class="dish-grid">{"".join(dish_card(d) for d in pdishes[:8])}</div></div>' if pdishes else ''
    else:
        personal_html='<div class="card" style="text-align:center;padding:30px"><p>登录后可获取个性化推荐</p><a href="/login" class="btn btn-p" style="margin-top:12px">去登录</a></div>'

    content=f'''
    <div class="card"><div class="card-hd">🔥 热门推荐</div><div class="dish-grid">{"".join(dish_card(d) for d in hot)}</div></div>
    {personal_html}'''
    return render('推荐', content, user)

@app.route('/profile')
@login_required
def profile_page():
    db=load_db()
    u=current_user()
    user=next((x for x in db['users'] if x['id']==u['id']),None)
    if not user: return redirect('/login')
    my_r=[r for r in db['reviews'] if r['user_id']==user['id']]
    my_f=[]
    for f in [fv for fv in db['favorites'] if fv['user_id']==user['id']]:
        d=next((x for x in db['dishes'] if x['id']==f['dish_id']),None)
        if d: my_f.append(d)

    reviews_html=''
    for r in my_r:
        d=next((x for x in db['dishes'] if x['id']==r['dish_id']),None)
        reviews_html+=f'''<div class="review-item">
        <div>{stars_html(r["rating"])} <strong>{d["name"] if d else "未知菜品"}</strong></div>
        <div class="rc">{r["content"]}</div>
        <span class="rt">{r["created_at"][:16].replace("T"," ")}</span></div>'''

    content=f'''
    <div class="card"><div class="card-hd">👤 个人信息</div>
      <p><strong>昵称：</strong>{user["nickname"]}</p>
      <p><strong>学号：</strong>{user["student_id"]}</p>
      <p><strong>角色：</strong>{"管理员" if user["role"]=="admin" else "普通用户"}</p>
      <p><strong>注册时间：</strong>{user["created_at"][:16].replace("T"," ")}</p></div>
    <div class="card"><div class="card-hd">📝 我的评价 ({len(my_r)})</div>
      {reviews_html or '<div class="empty">暂无评价</div>'}</div>
    <div class="card"><div class="card-hd">⭐ 我的收藏 ({len(my_f)})</div>
      <div class="dish-grid">{"".join(dish_card(d) for d in my_f) or '<div class="empty">暂无收藏</div>'}</div></div>'''
    return render('个人中心', content, user)

@app.route('/admin')
@login_required
@admin_only
def admin_page():
    db=load_db()
    u=current_user()
    user=next((x for x in db['users'] if x['id']==u['id']),None)
    tab=request.args.get('tab','stats')
    rcount=len(db['reviews'])
    avg_all=round(sum(r['rating'] for r in db['reviews'])/rcount,1) if rcount else 0

    # 统计
    cstats=[]
    for c in db['canteens']:
        ds=[d for d in db['dishes'] if d['canteen_id']==c['id']]
        dids=[d['id'] for d in ds]
        rs=[r for r in db['reviews'] if r['dish_id'] in dids]
        cstats.append({'name':c['name'],'dishCount':len(ds),'reviewCount':len(rs),'avgRating':round(sum(r['rating'] for r in rs)/len(rs),1) if rs else 0})

    # 分类统计
    cmap={}
    for d in db['dishes']:
        cat=d['category']
        if cat not in cmap: cmap[cat]={'count':0,'rsum':0,'rcount':0}
        cmap[cat]['count']+=1; cmap[cat]['rsum']+=d['avg_rating']; cmap[cat]['rcount']+=d['review_count']
    catstats=[{'name':k,'dishCount':v['count'],'avgRating':round(v['rsum']/v['count'],1) if v['count'] else 0,'reviewCount':v['rcount']} for k,v in cmap.items()]

    recent=sorted(db['reviews'],key=lambda r:r['id'],reverse=True)[:10]
    recent_html=''
    for r in recent:
        ru=next((x for x in db['users'] if x['id']==r['user_id']),None)
        rd=next((x for x in db['dishes'] if x['id']==r['dish_id']),None)
        recent_html+=f'<div class="review-item"><div class="rh"><span>{ru["nickname"] if ru else "?"} 评价 {rd["name"] if rd else "?"}</span><span class="rt">{r["created_at"][:16].replace("T"," ")}</span></div><div>{stars_html(r["rating"])} {r["content"]}</div></div>'

    dishes=db['dishes']
    cname={c['id']:c['name'] for c in db['canteens']}

    content=''
    if tab=='stats':
        content=f'''
        <h2 style="margin-bottom:16px">📊 管理后台</h2>
        <div class="tabs">
          <a href="/admin?tab=stats" class="tab active">📊 数据统计</a>
          <a href="/admin?tab=dishes" class="tab">🍽️ 菜品管理</a>
          <a href="/admin?tab=add" class="tab">➕ 添加菜品</a>
        </div>
        <div class="stat-grid">
          <div class="stat-card"><div class="sv">{len(db["users"])}</div><div class="sl">用户总数</div></div>
          <div class="stat-card"><div class="sv">{len(dishes)}</div><div class="sl">菜品总数</div></div>
          <div class="stat-card"><div class="sv">{rcount}</div><div class="sl">评价总数</div></div>
          <div class="stat-card"><div class="sv">{avg_all}</div><div class="sl">全站平均分</div></div>
        </div>
        <div class="card"><div class="card-hd">📈 各食堂数据对比</div><div class="chart-box" id="c1"></div></div>
        <div class="card"><div class="card-hd">📊 分类分布</div><div class="chart-box" id="c2"></div></div>
        <div class="card"><div class="card-hd">📋 最近评价</div>{recent_html}</div>
        <script>
        setTimeout(function(){{
          if(typeof echarts==='undefined')return;
          var c=echarts.init(document.getElementById("c1"));
          c.setOption({{tooltip:{{trigger:"axis"}},legend:{{data:["菜品数","评价数","平均分"]}},xAxis:{{type:"category",data:{json.dumps([s['name'] for s in cstats])}}},yAxis:[{{type:"value",name:"数量"}},{{type:"value",name:"评分",min:0,max:5}}],series:[{{name:"菜品数",type:"bar",data:{json.dumps([s['dishCount'] for s in cstats])},itemStyle:{{color:"#FFA726"}}}},{{name:"评价数",type:"bar",data:{json.dumps([s['reviewCount'] for s in cstats])},itemStyle:{{color:"#FF6B35"}}}},{{name:"平均分",type:"line",yAxisIndex:1,data:{json.dumps([s['avgRating'] for s in cstats])},itemStyle:{{color:"#4CAF50"}}}}]}});
          var c2=echarts.init(document.getElementById("c2"));
          c2.setOption({{tooltip:{{trigger:"item"}},series:[{{type:"pie",radius:["40%","70%"],data:{json.dumps([{'name':s['name'],'value':s['dishCount']} for s in catstats])}}}]}});
        }},100);
        </script>'''
    elif tab=='dishes':
        rows=''
        for d in dishes:
            rows+=f'''<tr>
            <td>{d['id']}</td><td><strong>{d['name']}</strong></td><td>{cname.get(d['canteen_id'],'-')}</td><td>{d['category']}</td><td>¥{d['price']}</td>
            <td>{stars_html(d['avg_rating'])} {d['avg_rating']}</td><td>{d['review_count']}</td>
            <td>{'<span style="color:#4CAF50">在售</span>' if d['is_available'] else '<span style="color:#999">下架</span>'}</td>
            <td><a href="/admin?tab=add&edit={d['id']}" class="btn-sm">编辑</a>
            <form method="post" action="/admin/dish/{d['id']}/delete" style="display:inline" onsubmit="return confirm('确定删除？')"><button class="btn-sm" style="border-color:#E53935;color:#E53935">删除</button></form></td></tr>'''
        content=f'''
        <h2 style="margin-bottom:16px">📊 管理后台</h2>
        <div class="tabs">
          <a href="/admin?tab=stats" class="tab">📊 数据统计</a>
          <a href="/admin?tab=dishes" class="tab active">🍽️ 菜品管理</a>
          <a href="/admin?tab=add" class="tab">➕ 添加菜品</a>
        </div>
        <div class="card"><div class="card-hd">全部菜品 ({len(dishes)})</div>
        <table class="table"><thead><tr><th>ID</th><th>名称</th><th>食堂</th><th>分类</th><th>价格</th><th>评分</th><th>评价数</th><th>状态</th><th>操作</th></tr></thead>
        <tbody>{rows}</tbody></table></div>'''
    elif tab=='add':
        edit_id=request.args.get('edit','')
        d={}; is_edit=False
        if edit_id:
            d=next((x for x in dishes if x['id']==int(edit_id)),{})
            is_edit=bool(d)
        cats=['盖饭','面食','小炒','主食','小吃','饮品','汤类','其他']
        content=f'''
        <h2 style="margin-bottom:16px">📊 管理后台</h2>
        <div class="tabs">
          <a href="/admin?tab=stats" class="tab">📊 数据统计</a>
          <a href="/admin?tab=dishes" class="tab">🍽️ 菜品管理</a>
          <a href="/admin?tab=add" class="tab active">➕ 添加菜品</a>
        </div>
        <div class="card" style="max-width:560px">
        <div class="card-hd">{'✏️ 编辑菜品' if is_edit else '➕ 添加新菜品'}</div>
        <form method="post" action="/admin/dish/{'edit' if is_edit else 'add'}">
        {"<input type=hidden name=id value="+str(d.get("id",""))+">" if is_edit else ""}
        <div class="fg"><label>菜品名称</label><input name="name" value="{d.get('name','')}" placeholder="如：宫保鸡丁" required></div>
        <div class="fg"><label>所属食堂</label><select name="canteen_id">{"".join(f'<option value="{c["id"]}" {"selected" if c["id"]==d.get("canteen_id") else ""}>{c["name"]}</option>' for c in db['canteens'])}</select></div>
        <div class="fg"><label>分类</label><select name="category">{"".join(f'<option value="{c}" {"selected" if c==d.get("category") else ""}>{c}</option>' for c in cats)}</select></div>
        <div class="fg"><label>价格 (元)</label><input name="price" type="number" value="{d.get('price','')}" placeholder="如：15" step="0.5" min="0" required></div>
        <div class="fg"><label>描述</label><textarea name="desc" placeholder="简短的菜品描述...">{d.get('desc','')}</textarea></div>
        {f'<div class="fg"><label>状态</label><select name="is_available"><option value="1" {"selected" if d.get("is_available")!=False else ""}>在售</option><option value="0" {"selected" if d.get("is_available")==False else ""}>下架</option></select></div>' if is_edit else ''}
        <button class="btn btn-p btn-block" type="submit">{'保存修改' if is_edit else '添加菜品'}</button>
        </form></div>'''
    return render('管理后台', content, user)

# ==================== 操作路由 ====================
@app.route('/fav/<int:dish_id>', methods=['POST'])
@login_required
def toggle_fav(dish_id):
    db=load_db()
    idx=next((i for i,f in enumerate(db['favorites']) if f['user_id']==request.user['id'] and f['dish_id']==dish_id),None)
    if idx is not None: db['favorites'].pop(idx)
    else: db['favorites'].append({'id':nid(db,'favorite'),'user_id':request.user['id'],'dish_id':dish_id})
    save_db(db)
    return redirect(request.referrer or '/')

@app.route('/review/<int:id>/like')
def like_review(id):
    db=load_db()
    r=next((x for x in db['reviews'] if x['id']==id),None)
    if r: r['likes']=r.get('likes',0)+1; save_db(db)
    return redirect(request.referrer or '/')

@app.route('/review/<int:id>/delete', methods=['POST'])
@login_required
def delete_review(id):
    db=load_db()
    idx=next((i for i,r in enumerate(db['reviews']) if r['id']==id),None)
    if idx is not None:
        r=db['reviews'][idx]
        if r['user_id']==request.user['id'] or request.user.get('role')=='admin':
            did=r['dish_id']
            db['reviews'].pop(idx)
            dish=next((d for d in db['dishes'] if d['id']==did),None)
            if dish:
                all_r=[x for x in db['reviews'] if x['dish_id']==did]
                dish['avg_rating']=round(sum(x['rating'] for x in all_r)/len(all_r),1) if all_r else 0
                dish['review_count']=len(all_r)
            save_db(db)
    return redirect(request.referrer or '/')

@app.route('/admin/dish/add', methods=['POST'])
@login_required
@admin_only
def admin_add_dish():
    db=load_db()
    dish={'id':nid(db,'dish'),'canteen_id':int(request.form['canteen_id']),'name':request.form['name'].strip(),'category':request.form['category'],'price':float(request.form['price']),'desc':request.form.get('desc','').strip(),'image':'','avg_rating':0,'review_count':0,'is_available':True,'created_at':datetime.now().isoformat()}
    db['dishes'].append(dish); save_db(db)
    return redirect('/admin?tab=dishes')

@app.route('/admin/dish/edit', methods=['POST'])
@login_required
@admin_only
def admin_edit_dish():
    db=load_db()
    did=int(request.form['id'])
    dish=next((d for d in db['dishes'] if d['id']==did),None)
    if dish:
        dish['name']=request.form['name'].strip()
        dish['canteen_id']=int(request.form['canteen_id'])
        dish['category']=request.form['category']
        dish['price']=float(request.form['price'])
        dish['desc']=request.form.get('desc','').strip()
        dish['is_available']=request.form.get('is_available','1')=='1'
        save_db(db)
    return redirect('/admin?tab=dishes')

@app.route('/admin/dish/<int:id>/delete', methods=['POST'])
@login_required
@admin_only
def admin_delete_dish(id):
    db=load_db()
    db['dishes']=[d for d in db['dishes'] if d['id']!=id]
    db['reviews']=[r for r in db['reviews'] if r['dish_id']!=id]
    db['favorites']=[f for f in db['favorites'] if f['dish_id']!=id]
    save_db(db)
    return redirect('/admin?tab=dishes')

# ==================== 美食日记 ====================
@app.route('/diary')
@login_required
def diary_page():
    db=load_db()
    u=current_user()
    user=next((x for x in db['users'] if x['id']==u['id']),None)
    if not user: return redirect('/login')

    my_reviews=sorted([r for r in db['reviews'] if r['user_id']==user['id']],key=lambda r:r['id'],reverse=True)

    # 按日期分组
    diary_entries={}
    for r in my_reviews:
        d=next((x for x in db['dishes'] if x['id']==r['dish_id']),None)
        canteen=None
        if d: canteen=next((c for c in db['canteens'] if c['id']==d['canteen_id']),None)
        date_key=r['created_at'][:10]  # YYYY-MM-DD
        if date_key not in diary_entries:
            diary_entries[date_key]=[]
        diary_entries[date_key].append({'review':r,'dish':d,'canteen':canteen})

    # 统计
    photo_count=len([r for r in my_reviews if r.get('image')])
    total_dishes=len(set(r['dish_id'] for r in my_reviews))

    diary_html=''
    for date_key in sorted(diary_entries.keys(),reverse=True):
        entries=diary_entries[date_key]
        dt=datetime.strptime(date_key,'%Y-%m-%d')
        month_str=f"{dt.month}月"
        day_str=str(dt.day)
        entries_html=''
        for e in entries:
            r=e['review']; d=e['dish']; c=e['canteen']
            img_html=''
            if r.get('image'):
                img_html=f'<img src="/static/uploads/{r["image"]}" class="diary-img" onclick="openImg(this.src)" alt="菜品实拍">'
            entries_html+=f'''
            <div class="diary-entry">
              <div style="min-width:60px;text-align:center;font-size:12px;color:var(--tl);padding-top:4px">🕐 {r["created_at"][11:16]}</div>
              <div class="diary-content">
                <a href="/dish/{d["id"]}" class="dish-link" style="text-decoration:none">🍽️ {d["name"] if d else "未知菜品"}</a>
                <span style="font-size:12px;color:var(--tl);margin-left:8px">{c["name"] if c else ""}</span>
                <div style="margin:4px 0">{stars_html(r["rating"])}</div>
                <div style="font-size:14px;line-height:1.6;color:var(--t)">{r["content"]}</div>
                {img_html}
              </div></div>'''
        diary_html+=f'''
        <div class="card">
          <div style="display:flex;align-items:center;gap:12px;margin-bottom:16px;padding-bottom:12px;border-bottom:2px solid var(--p)">
            <div style="text-align:center">
              <div style="font-size:32px;font-weight:700;color:var(--p);line-height:1">{day_str}</div>
              <div style="font-size:14px;color:var(--tl)">{month_str}</div>
            </div>
            <div style="font-size:13px;color:var(--tl)">{date_key} · {len(entries)}条记录</div>
          </div>
          {entries_html}
        </div>'''
        if not entries_html: diary_html=''

    content=f'''
    <div class="stat-grid" style="margin-bottom:16px">
      <div class="stat-card"><div class="sv">{len(my_reviews)}</div><div class="sl">总评价数</div></div>
      <div class="stat-card"><div class="sv">{photo_count}</div><div class="sl">📸 晒图数</div></div>
      <div class="stat-card"><div class="sv">{total_dishes}</div><div class="sl">品尝菜品</div></div>
      <div class="stat-card"><div class="sv">{round(sum(r["rating"] for r in my_reviews)/len(my_reviews),1) if my_reviews else 0}</div><div class="sl">平均评分</div></div>
    </div>
    <h2 style="margin:16px 0;color:var(--p)">📔 我的美食日记</h2>
    {diary_html or '<div class="card"><div class="empty">还没有记录，<a href="/" style="color:var(--p)">去探索美食</a>吧！🕵️</div></div>'}
    '''
    return render('美食日记', content, user)

# ==================== 发现页（图片墙） ====================
@app.route('/discover')
def discover_page():
    db=load_db()
    u=current_user(); user=None
    if u: user=next((x for x in db['users'] if x['id']==u['id']),None)

    # 获取所有带图片的评价
    photo_reviews=[r for r in db['reviews'] if r.get('image')]
    photo_reviews.sort(key=lambda r:r['id'],reverse=True)

    cards_html=''
    for r in photo_reviews:
        ru=next((x for x in db['users'] if x['id']==r['user_id']),None)
        rd=next((x for x in db['dishes'] if x['id']==r['dish_id']),None)
        canteen=None
        if rd: canteen=next((c for c in db['canteens'] if c['id']==rd['canteen_id']),None)
        cards_html+=f'''
        <div class="photo-card" onclick="location.href='/dish/{rd["id"]}'">
          <img src="/static/uploads/{r["image"]}" alt="{rd["name"] if rd else "菜品"}" loading="lazy">
          <div class="photo-info">
            <div class="photo-dish">🍽️ {rd["name"] if rd else "未知菜品"}</div>
            <div class="photo-meta">
              <span>👤 {ru["nickname"] if ru else "匿名"}</span>
              <span>{stars_html(r["rating"])}</span>
            </div>
            <div class="photo-meta" style="margin-top:2px">
              <span>📍 {canteen["name"] if canteen else ""} · ¥{rd["price"] if rd else "?"}</span>
              <span style="font-size:11px">{r["created_at"][:10]}</span>
            </div>
            {'<div class="photo-text">'+r["content"]+'</div>' if r["content"] else ''}
          </div>
        </div>'''

    content=f'''
    <div style="margin-bottom:16px">
      <h2 style="color:var(--p)">📸 美食发现</h2>
      <p style="color:var(--tl);margin-top:4px">共 {len(photo_reviews)} 张晒图，看看大家都在吃什么 🤤</p>
    </div>
    <div class="photo-grid">
      {cards_html or '<div class="card" style="text-align:center;padding:40px;grid-column:1/-1"><p style="font-size:16px;color:var(--tl)">还没有人晒图，快来发布第一张吧！📸</p><a href="/" class="btn btn-p" style="margin-top:12px">去探索美食</a></div>'}
    </div>
    '''
    return render('美食发现', content, user)

# ==================== 启动 ====================
if __name__=='__main__':
    import threading, sys
    port = int(os.environ.get('PORT', 3000))
    print(f'校园食堂菜品评价与就餐推荐系统已启动')

    def run_flask():
        app.run(host='0.0.0.0', port=port, debug=False)

    # 判断是否打包成exe（打包后不含命令行参数时直接桌面窗口运行）
    use_gui = '--web' not in sys.argv

    if use_gui:
        try:
            import webview
            t = threading.Thread(target=run_flask, daemon=True)
            t.start()
            import time; time.sleep(0.5)
            webview.create_window('校园食堂菜品评价与就餐推荐系统', f'http://127.0.0.1:{port}',
                                  width=1100, height=750, min_size=(800, 500))
            webview.start()
        except ImportError:
            print('缺少pywebview，使用浏览器模式')
            run_flask()
    else:
        run_flask()
