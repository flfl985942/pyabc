from playwright.sync_api import sync_playwright
import time
import os
import json
import threading

PERSIST_FILE = os.path.join(os.getcwd(), "tax_assignments.json")

def save_snapshot(page):
    """从页面读取相关 localStorage 条目并写到本地文件"""
    try:
        snapshot = page.evaluate(
            """() => {
                const entries = {};
                for (let i = 0; i < localStorage.length; i++) {
                    const k = localStorage.key(i);
                    if (!k) continue;
                    if (k.includes('_TASK_') || k === 'GLOBAL_TAX_HISTORY') {
                        entries[k] = localStorage.getItem(k);
                    }
                }
                return entries;
            }"""
        )
        with open(PERSIST_FILE, "w", encoding="utf-8") as f:
            json.dump(snapshot or {}, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f">>> 保存 snapshot 失败: {e}")

def restore_snapshot(page):
    """如果存在本地文件则恢复到页面 localStorage"""
    if not os.path.exists(PERSIST_FILE):
        return
    try:
        with open(PERSIST_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        # 将字典传给页面并写入 localStorage
        page.evaluate("data => { Object.entries(data).forEach(([k,v])=> localStorage.setItem(k, v)); }", data)
        print(">>> 已从本地文件恢复 localStorage 条目。")
    except Exception as e:
        print(f">>> 恢复 snapshot 失败: {e}")

def login_and_run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, args=['--start-maximized'])
        context = browser.new_context(no_viewport=True)
        page = context.new_page()

        print(">>> 正在启动程序...")
        page.goto("http://112.111.3.73:8080/eurbanpro/index.html#/login")
        
        # 自动填入
        page.fill("#basic_username", "ljxswjjb02")
        page.fill("#basic_psw", "Lf121212@")
        
        print(">>> 请手动登录并进入待反馈列表...")

        try:
            # 等待跳转到工作台
            page.wait_for_function("() => !window.location.href.includes('login')", timeout=120000)
            time.sleep(2)
            # 跳转到你提供的长链接
            target_url = "http://112.111.3.73:8080/eurbanpro/index.html#/workbench/rec/rec-task?code=dispatch&name=%E8%AF%89%E6%B1%82%E5%A4%84%E7%BD%AE&layout=mimic&layoutOnly=list&sysWaterMark=false"
            page.goto(target_url)

            # 先从本地文件恢复 localStorage（如果存在）
            restore_snapshot(page)

            # 注入脚本：自定义下拉建议（避免原生 datalist 失焦导致消失）
            page.evaluate("""
                () => {
                    function cleanText(s) { return (s || '').replace(/\\u00A0/g, ' ').replace(/\\s+/g, ' ').trim(); }
                    function makeKey(taskId) {
                        const scope = location.origin + '_' + (location.hash ? location.hash.split('?')[0] : location.pathname);
                        return `${scope}_TASK_${taskId}`;
                    }
                    function refreshGlobalHistory() {
                        return JSON.parse(localStorage.getItem('GLOBAL_TAX_HISTORY') || '[]');
                    }
                    function saveToHistory(v) {
                        if (!v) return;
                        let h = JSON.parse(localStorage.getItem('GLOBAL_TAX_HISTORY') || '[]');
                        if (!h.includes(v)) {
                            h.push(v);
                            localStorage.setItem('GLOBAL_TAX_HISTORY', JSON.stringify(h));
                        }
                    }
                    function detectTaskId(row, fallbackIndex) {
                        const dataKey = row.getAttribute('data-row-key') || row.getAttribute('data-id') || row.getAttribute('data-key');
                        if (dataKey && dataKey.trim()) return cleanText(dataKey);
                        const a = row.querySelector('a[href]');
                        if (a) {
                            const href = a.getAttribute('href') || '';
                            const match = href.match(/(\\d{4,})/);
                            if (match) return match[1];
                            const txt = cleanText(a.innerText);
                            if (txt.length >= 3) return txt;
                        }
                        const tds = row.querySelectorAll('td');
                        if (tds && tds.length > fallbackIndex) {
                            const text = cleanText(tds[fallbackIndex].innerText || '');
                            const m = text.match(/([A-Za-z0-9\\-]{4,})/);
                            if (m) return m[1];
                        }
                        const allText = cleanText(Array.from(row.querySelectorAll('td')).map(td => td.innerText).join(' '));
                        const m2 = allText.match(/([A-Za-z0-9\\-]{5,})/);
                        if (m2) return m2[1];
                        return null;
                    }

                    // 样式：输入框 + 自定义下拉
                    if (!document.getElementById('tax-input-style')) {
                        const style = document.createElement('style');
                        style.id = 'tax-input-style';
                        style.innerHTML = `
                            .tax-pretty-cell { padding:6px 8px; border-bottom:1px solid #f0f0f0; text-align:center; vertical-align: middle; position: relative; }
                            .tax-input {
                                width:100%;
                                max-width:140px;
                                height:32px;
                                padding:4px 11px;
                                font-size:14px;
                                color: rgba(0,0,0,0.85);
                                background: #fff;
                                border: 1px solid #d9d9d9;
                                border-radius: 2px;
                                box-sizing: border-box;
                                transition: all 0.12s ease;
                                outline: none;
                                display: inline-block;
                                vertical-align: middle;
                            }
                            .tax-input:focus {
                                border-color: #40a9ff;
                                box-shadow: 0 0 0 4px rgba(24,144,255,0.06);
                            }
                            .tax-input.saved {
                                background: #f6ffed;
                                border-color: #b7eb8f;
                            }
                            .tax-suggest {
                                position: absolute;
                                left: 8px;
                                right: 8px;
                                top: 40px;
                                z-index: 9999;
                                background: #fff;
                                border: 1px solid #e8e8e8;
                                border-radius: 4px;
                                box-shadow: 0 6px 16px rgba(0,0,0,0.08);
                                max-height: 200px;
                                overflow: auto;
                                padding: 6px 0;
                                box-sizing: border-box;
                                font-size: 14px;
                            }
                            .tax-suggest-item {
                                padding: 6px 12px;
                                cursor: pointer;
                                white-space: nowrap;
                                overflow: hidden;
                                text-overflow: ellipsis;
                                color: rgba(0,0,0,0.85);
                            }
                            .tax-suggest-item:hover {
                                background: #f5f5f5;
                            }
                            .tax-suggest-empty {
                                padding: 8px 12px;
                                color: rgba(0,0,0,0.35);
                            }
                        `;
                        document.head.appendChild(style);
                    }

                    // Render suggestions for an input based on GLOBAL_TAX_HISTORY
                    function renderSuggestionsForInput(input) {
                        let dl = input._taxSuggest;
                        const history = refreshGlobalHistory();
                        const q = (input.value || '').trim().toLowerCase();
                        // filter history by startsWith or contains
                        const items = q ? history.filter(h => h.toLowerCase().includes(q)) : history.slice().reverse();
                        if (!dl) {
                            dl = document.createElement('div');
                            dl.className = 'tax-suggest';
                            input._taxSuggest = dl;
                            // insert into the td (which is relative)
                            const td = input.closest('.tax-pretty-cell');
                            if (td) td.appendChild(dl);
                            else input.parentElement.appendChild(dl);
                        }
                        dl.innerHTML = '';
                        if (!items || items.length === 0) {
                            const empty = document.createElement('div');
                            empty.className = 'tax-suggest-empty';
                            empty.innerText = '无历史';
                            dl.appendChild(empty);
                            return;
                        }
                        items.forEach(v => {
                            const it = document.createElement('div');
                            it.className = 'tax-suggest-item';
                            it.innerText = v;
                            // use mousedown so it fires before input blur
                            it.addEventListener('mousedown', (ev) => {
                                ev.preventDefault();
                                ev.stopPropagation();
                                input.value = v;
                                // 立即保存
                                try { 
                                    const key = makeKey(input.getAttribute('data-task-id'));
                                    localStorage.setItem(key, v);
                                    saveToHistory(v);
                                } catch (e) { console.error(e); }
                                input.classList.add('saved');
                                hideSuggestionsForInput(input);
                            });
                            dl.appendChild(it);
                        });
                    }

                    function showSuggestionsForInput(input) {
                        renderSuggestionsForInput(input);
                        const dl = input._taxSuggest;
                        if (dl) dl.style.display = 'block';
                    }
                    function hideSuggestionsForInput(input) {
                        const dl = input._taxSuggest;
                        if (dl) dl.style.display = 'none';
                    }

                    // Click outside to hide any suggestion lists
                    document.addEventListener('click', (e) => {
                        // if click inside an input or its suggest, do nothing
                        const tgt = e.target;
                        if (!tgt) return;
                        if (tgt.closest && (tgt.closest('.tax-input') || tgt.closest('.tax-suggest'))) return;
                        // hide all
                        document.querySelectorAll('.tax-suggest').forEach(d => d.style.display = 'none');
                    });

                    function inject() {
                        const rows = document.querySelectorAll('tr');
                        if (!rows || rows.length === 0) return;

                        // 找表头并定位插入位置（诉求标题后）
                        let headerRow = null;
                        let titleIndex = 3;
                        let guessedTaskIndex = 2;
                        rows.forEach(row => {
                            const ths = row.querySelectorAll('th');
                            if (ths && ths.length > 0) {
                                headerRow = row;
                                ths.forEach((th, i) => {
                                    const txt = cleanText(th.innerText || '');
                                    if (txt.includes('诉求标题')) titleIndex = i;
                                    if (txt.includes('诉求编号') || txt.includes('编号') || txt.includes('受理编号')) guessedTaskIndex = i;
                                });
                            }
                        });

                        // 在 colgroup 插入 col，位置为 titleIndex + 1，宽度 140px（如果还没插入）
                        function ensureColAt(index, widthPx) {
                            const headerTable = document.querySelector('.ant-table-header table');
                            const bodyTable = document.querySelector('.ant-table-body table');
                            [headerTable, bodyTable].forEach(table => {
                                if (!table) return;
                                const cg = table.querySelector('colgroup');
                                if (!cg) return;
                                const cols = cg.querySelectorAll('col');
                                const exists = Array.from(cols).some(c => c.classList && c.classList.contains('tax-col'));
                                if (exists) return;
                                const col = document.createElement('col');
                                col.className = 'tax-col';
                                col.style.width = (widthPx || 140) + 'px';
                                const insertBefore = cols[index];
                                if (insertBefore) cg.insertBefore(col, insertBefore);
                                else cg.appendChild(col);
                            });
                        }
                        ensureColAt(titleIndex + 1, 140);

                        if (headerRow && !document.getElementById('pretty-tax-header')) {
                            const newTh = document.createElement('th');
                            newTh.id = 'pretty-tax-header';
                            newTh.innerText = '税管员分派';
                            newTh.style.cssText = "background:#fafafa; color:rgba(0,0,0,0.85); font-weight:500; padding:12px; border-bottom:1px solid #f0f0f0; min-width:140px; text-align:center;";
                            if (headerRow.children.length > titleIndex + 1) headerRow.insertBefore(newTh, headerRow.children[titleIndex + 1]);
                            else headerRow.appendChild(newTh);
                        }

                        // 遍历数据行
                        rows.forEach(row => {
                            if (row.classList && row.classList.contains('ant-table-measure-row')) return;
                            const tds = row.querySelectorAll('td');
                            if (!tds || tds.length === 0) return;
                            if (row.querySelector('.tax-pretty-cell')) return;
                            const taskId = detectTaskId(row, guessedTaskIndex);
                            if (!taskId) return;

                            const newTd = document.createElement('td');
                            newTd.className = 'tax-pretty-cell';
                            // 防止单元格点击冒泡到行
                            newTd.addEventListener('click', (e) => { e.stopPropagation(); });

                            const input = document.createElement('input');
                            input.className = 'tax-input';
                            input.placeholder = '分派人...';
                            input.setAttribute('data-task-id', taskId);

                            // 阻止输入框的点击/按下冒泡到行（关键）
                            input.addEventListener('pointerdown', (e) => { e.stopPropagation(); });
                            input.addEventListener('mousedown', (e) => { e.stopPropagation(); });
                            input.addEventListener('click', (e) => { e.stopPropagation(); });

                            // 回显
                            const saved = localStorage.getItem(makeKey(taskId));
                            if (saved) {
                                input.value = saved;
                                input.classList.add('saved');
                            }

                            // 事件：focus 显示建议，input 过滤，blur 保存并延时隐藏（短延时防止与 mousedown 冲突）
                            input.addEventListener('focus', () => {
                                showSuggestionsForInput(input);
                            });
                            input.addEventListener('input', () => {
                                renderSuggestionsForInput(input);
                                showSuggestionsForInput(input);
                            });
                            input.addEventListener('keydown', (e) => {
                                if (e.key === 'Enter') {
                                    e.preventDefault();
                                    const v = (input.value || '').trim();
                                    if (v) {
                                        try {
                                            localStorage.setItem(makeKey(taskId), v);
                                            saveToHistory(v);
                                            input.classList.add('saved');
                                        } catch (err) { console.error(err); }
                                    } else {
                                        localStorage.removeItem(makeKey(taskId));
                                        input.classList.remove('saved');
                                    }
                                    hideSuggestionsForInput(input);
                                    input.blur();
                                } else if (e.key === 'Escape') {
                                    hideSuggestionsForInput(input);
                                    input.blur();
                                }
                            });
                            input.addEventListener('blur', () => {
                                // 延迟隐藏，以便 mousedown handler 能先执行
                                setTimeout(() => {
                                    const v = (input.value || '').trim();
                                    if (v) {
                                        try {
                                            localStorage.setItem(makeKey(taskId), v);
                                            saveToHistory(v);
                                            input.classList.add('saved');
                                        } catch (err) { console.error(err); }
                                    } else {
                                        localStorage.removeItem(makeKey(taskId));
                                        input.classList.remove('saved');
                                    }
                                    hideSuggestionsForInput(input);
                                }, 160);
                            });

                            newTd.appendChild(input);
                            if (tds.length > titleIndex + 1) row.insertBefore(newTd, row.children[titleIndex + 1]);
                            else row.appendChild(newTd);
                        });
                    }

                    const observer = new MutationObserver((mutations) => {
                        if (window.__tax_inject_timeout) clearTimeout(window.__tax_inject_timeout);
                        window.__tax_inject_timeout = setTimeout(() => {
                            try { inject(); } catch (err) { console.error('tax inject err', err); }
                        }, 250);
                    });
                    observer.observe(document.body, { childList: true, subtree: true });

                    // 首次注入
                    inject();
                }
            """)
           

            
  