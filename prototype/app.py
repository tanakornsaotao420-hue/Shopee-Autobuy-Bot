import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime, timedelta
from pathlib import Path
from engine import Engine, BANGKOK, SCENARIOS

root = tk.Tk()
root.title('Campaign Planner 0.2 • CHECKOUT SIMULATOR')
root.geometry('1100x820')
root.minsize(960, 740)
root.configure(bg='#f5f6fa')
style = ttk.Style()
style.theme_use('clam')
style.configure('.', font=('Tahoma', 10))
base = Path(__file__).resolve().parent
engine = Engine(base / 'simulation.sqlite3')
ttk.Label(root, text='Campaign Planner', font=('Tahoma', 22, 'bold')).pack(anchor='w', padx=24, pady=(18, 4))
ttk.Label(root, text='โหมดจำลองเท่านั้น • ไม่เชื่อม Shopee • ไม่ตัดบัตร • เวลาประเทศไทย UTC+7', foreground='#bc411b').pack(anchor='w', padx=24)
form = ttk.Frame(root, padding=20)
form.pack(fill='x')
fields = [
 ('campaign','ชื่อแคมเปญ','ทดลอง 11.11'), ('product','ลิงก์หรือชื่อสินค้า','สินค้าทดลอง'),
 ('variant','รุ่น / สี / ขนาด','สีดำ'), ('quantity','จำนวน','1'),
 ('price','ราคาต่อชิ้น (บาท)','1200'), ('shipping','ค่าส่ง (บาท)','40'),
 ('discount','ส่วนลดรวมทันที (บาท)','300'), ('coupon','โค้ดจำลอง','DEMO300'),
 ('cap','เพดานยอดตัดบัตรต่อคำสั่งซื้อ','1000'), ('budget','งบรวมแคมเปญ','2000'),
 ('start','เวลาเริ่ม (เวลาประเทศไทย)',(datetime.now(BANGKOK)+timedelta(minutes=2)).strftime('%Y-%m-%d %H:%M:%S')),
 ('window','ระยะเวลาอนุญาต (วินาที)','300'),
 ('address','ชื่อเรียกที่อยู่ (ไม่ต้องกรอกที่อยู่จริง)','บ้าน'), ('card','ชื่อเรียกบัตร (ห้ามกรอกเลขบัตร)','บัตรหลัก')]
values = {}
for i, (key, label, default) in enumerate(fields):
    row, col = divmod(i, 2)
    ttk.Label(form, text=label).grid(row=row, column=col*2, sticky='w', pady=5, padx=(0,10))
    values[key] = tk.StringVar(value=default)
    ttk.Entry(form, textvariable=values[key], width=29).grid(row=row, column=col*2+1, sticky='ew', padx=(0,20))
form.columnconfigure(1, weight=1)
form.columnconfigure(3, weight=1)
required = tk.BooleanVar(value=True)
ttk.Checkbutton(form, text='ต้องใช้คูปองได้จึงซื้อ', variable=required).grid(row=7, column=0, columnspan=2, sticky='w')
scenario = tk.StringVar(value='success')
ttk.Combobox(form, textvariable=scenario, values=SCENARIOS, state='readonly', width=25).grid(row=7, column=3, sticky='ew')
ttk.Label(form, text='สถานการณ์จำลอง').grid(row=7, column=2, sticky='w')
ttk.Label(root, text='success = สำเร็จ | sold_out = หมด | coupon_missing = โค้ดหมด | price_changed = เกินงบ\nchallenge = รอยืนยัน | unknown / payment_page_only = ไม่ทราบผล | declined = บัตรปฏิเสธ\nwrong_card / ambiguous_card = บัตรผิด / หลายใบ | wrong_variant / extra_item = สินค้าไม่ตรง | stale_quote = ข้อมูลเก่า').pack(anchor='w', padx=24)
buttons = ttk.Frame(root, padding=(20,10))
buttons.pack(fill='x')
tree = ttk.Treeview(root, columns=('product','time','status','amount'), show='headings', height=6, selectmode='browse')
for key, label, width in [('product','สินค้า',250),('time','เวลาไทย',190),('status','สถานะจำลอง',190),('amount','ยอดที่กันงบ (บาท)',140)]:
    tree.heading(key, text=label)
    tree.column(key, width=width)
tree.pack(fill='both', expand=True, padx=20)
log = tk.Text(root, height=6, font=('Tahoma',10), state='disabled')
log.pack(fill='x', padx=20, pady=10)

def refresh():
    selected = tree.selection()
    tree.delete(*tree.get_children())
    for job, p, state, amount, receipt in engine.rows():
        tree.insert('', 'end', iid=job, values=(p['product'], p['start'][:19].replace('T',' '), state, f'{amount/100:.2f}'))
    if selected and tree.exists(selected[0]):
        tree.selection_set(selected[0])
    show_log()

def show_log(event=None):
    selected = tree.selection()
    log.configure(state='normal')
    log.delete('1.0','end')
    if selected:
        for at, msg in engine.events(selected[0]):
            log.insert('end', at[11:19] + '  ' + msg + '\n')
    log.configure(state='disabled')

def action(fn):
    try:
        fn()
        refresh()
    except Exception as exc:
        messagebox.showerror('ตรวจสอบข้อมูล', str(exc))

def add():
    p = {k:v.get().strip() for k,v in values.items()}
    p['start'] = datetime.strptime(p['start'], '%Y-%m-%d %H:%M:%S').replace(tzinfo=BANGKOK).isoformat()
    p.update(required_coupon=required.get(), scenario=scenario.get())
    job = engine.add(p)
    refresh()
    tree.selection_set(job)

def selected():
    if not tree.selection():
        raise ValueError('กรุณาเลือกงานจากตาราง')
    return tree.selection()[0]

ttk.Button(buttons, text='บันทึกและตั้งเวลาจำลอง', command=lambda:action(add)).pack(side='left', padx=4)
ttk.Button(buttons, text='หยุดงานที่เลือก', command=lambda:action(lambda:engine.cancel(selected()))).pack(side='left', padx=4)
ttk.Button(buttons, text='จำลองยืนยันสำเร็จ', command=lambda:action(lambda:engine.resolve(selected(),True))).pack(side='left', padx=4)
ttk.Button(buttons, text='จำลองยืนยันล้มเหลว', command=lambda:action(lambda:engine.resolve(selected(),False))).pack(side='left', padx=4)
ttk.Label(root, text='ต้องเปิดโปรแกรมและเครื่องไว้เพื่อเดินเวลา • ปิดแล้วเปิดใหม่จะอ่านงานเดิม • ไม่มีบริการเบื้องหลัง', foreground='#555').pack(pady=(0,10))
tree.bind('<<TreeviewSelect>>', show_log)

def tick():
    try:
        engine.tick()
        refresh()
    except Exception as exc:
        root.title('Campaign Planner — หยุดตัวตั้งเวลา: ' + str(exc))
        messagebox.showerror('ตัวตั้งเวลาหยุดทำงาน', str(exc))
        return
    root.after(1000, tick)

tick()
root.mainloop()
