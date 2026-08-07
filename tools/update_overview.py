#!/usr/bin/env python3
"""更新概况页（index.html）数据：公司市值（公司与深度研究一一对应，列表以页面 COMPANIES 为准）。
优先 WindPy；Wind 取不到的代码会列出来，再用 gangtise 兜底或保留原值。
用法：python3 tools/update_overview.py [--dry-run]
"""
import re, sys, datetime
from pathlib import Path

HTML = Path(__file__).resolve().parent.parent / 'index.html'
DRY = '--dry-run' in sys.argv

# 特殊代码候选（默认先试 {t}.O 再 {t}.N）
SPECIAL = {
    'BRK.B': ['BRK_B.N'],   # Wind 伯克希尔 B 股代码是 BRK_B.N（下划线）
}

def main():
    html = HTML.read_text(encoding='utf-8')

    tickers = re.findall(r"\{t:'([^']+)'", html)
    print(f'共 {len(tickers)} 个 ticker')

    from WindPy import w
    w.start()

    # 美股最新收盘日：北京时间白天跑脚本时“今天”是占位值，结束日期取昨天；
    # 只拉最近 15 天标普日线来确定最新交易日（省额度，指数行情本身不上页面）
    end = datetime.date.today() - datetime.timedelta(days=1)
    d = w.wsd('SPX.GI', 'close', (end - datetime.timedelta(days=15)).isoformat(), end.isoformat(), '')
    pts = [(t, v) for t, v in zip(d.Times, d.Data[0]) if v]
    latest_date = pts[-1][0]
    print(f'数据日期: {latest_date}')

    # ---------- 2. 公司市值 ----------
    caps, failed = {}, []
    def pull(codes_map):  # codes_map: wind_code -> ticker
        if not codes_map: return
        r = w.wsd(','.join(codes_map), 'mkt_cap_ard',
                  latest_date.isoformat(), latest_date.isoformat(), 'Currency=USD')
        if r.ErrorCode != 0:
            print(f'!! 批量市值失败: {r.Data}'); return
        for cd, v in zip(r.Codes, r.Data[0]):   # 单指标多代码：Data 只有一行
            t = codes_map.get(cd) or codes_map.get(cd.upper())
            if not t:
                print(f'!! Wind 返回了未请求的代码 {cd}，已跳过'); continue
            if v: caps[t] = round(v / 1e9)          # 美元 -> 十亿美元
            else: failed.append(t)

    todo = {t: [f'{t}.O', f'{t}.N'] for t in tickers}
    todo.update({t: SPECIAL[t] for t in SPECIAL if t in tickers})
    # 第一轮：默认第一候选
    pull({cands[0]: t for t, cands in todo.items()})
    # 后续轮：失败代码换下一候选
    retry = failed; failed = []
    for cd_idx in range(1, 3):
        batch = {todo[t][cd_idx]: t for t in retry if len(todo[t]) > cd_idx}
        pull(batch)
        retry, failed = failed, []
    failed = retry
    print(f'取到市值 {len(caps)}/{len(tickers)}；失败: {failed}')
    w.stop()

    # ---------- 3. 写回 HTML ----------
    # 公司 cap 就地替换
    def fix_cap(m):
        t, cap = m.group(1), m.group(2)
        return m.group(0).replace(f'cap:{cap}', f'cap:{caps[t]}') if t in caps else m.group(0)
    html = re.sub(r"\{t:'([^']+)'[^}]*?cap:(\d+)", fix_cap, html)

    # 日期文案（页头「数据更新」）
    ds = latest_date.isoformat()
    html = re.sub(r'(<span>数据更新</span>\s*<strong>)\d{4}-\d{2}-\d{2}', rf'\g<1>{ds}', html)

    if DRY:
        print('--- dry-run，不写文件 ---')
    else:
        HTML.write_text(html, encoding='utf-8')
        print(f'已写回 {HTML}（数据日期 {ds}）')
    if failed:
        print('以下代码 Wind 未取到，保留原值（可换 gangtise 兜底）:', failed)

if __name__ == '__main__':
    main()
