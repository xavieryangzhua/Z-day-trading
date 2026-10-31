"""Trading workspace. Broker execution is enabled only through the paper service."""
import json
from datetime import datetime, timezone

import pandas as pd
import streamlit as st
import store


def database_rows():
    folder = store.ROOT / 'data/external/ibkr'
    rows = []
    for manifest in sorted(folder.glob('*/sources.json')):
        for source in json.loads(manifest.read_text()):
            rows.append({'标的': source['symbol'], '开始': source['first_bar'][:10],
                         '结束': source['last_bar'][:10], '交易日': source['days'],
                         '分钟K线': source['rows'], '来源': 'IBKR'})
    return rows


def render(items):
    mode = st.radio('模式', ['数据库', '模拟交易', 'Live 交易'], horizontal=True)
    if mode == '数据库':
        rows = database_rows()
        if rows:
            st.dataframe(pd.DataFrame(rows), hide_index=True, width='stretch')
        else:
            st.info('暂无行情数据库。')
        st.caption('1分钟正常交易时段数据；回测结果在「排名」和「个股排名」。')
        return
    if mode == 'Live 交易':
        st.info('Live 交易尚未启用。')
        return
    from importlib.util import find_spec
    if any(find_spec(name) is None for name in ("paper_control", "paper_store", "paper_worker")):
        st.info("Paper交易程序仅在本地运行，请在本机网页查看和操作。")
        return
    render_paper()


@st.cache_data(ttl=30)
def eligible():
    import paper_store
    return paper_store.candidates()


def render_paper():
    import paper_store as book
    import paper_control
    st.caption('IBKR Paper · 仅模拟账户 · 当日到期Call · 每次1张')
    if st.button('检查 Paper 连接'):
        with st.spinner('连接本机 Gateway…'):
            try:st.session_state['paper_probe']=paper_control.probe()
            except Exception as exc:st.session_state['paper_probe']={'connected':False,'message':str(exc)}
    probe=st.session_state.get('paper_probe')
    if probe:
        if probe['connected']:st.success(f"{probe.get('account','Paper')} · {probe['message']}")
        else:st.error(probe['message'])
        if probe.get('portfolio'):
            st.caption('Paper账户持仓快照 · '+probe.get('time','')+' · 点击连接检查可更新')
            st.dataframe(pd.DataFrame(probe['portfolio']).rename(columns={'symbol':'标的','contract':'合约','quantity':'数量','market_price':'估值报价','unrealized_pnl':'未实现盈亏 ($)'}),hide_index=True,width='stretch')
    st.caption('先在本机IB Gateway登录Paper；网页使用4002端口。连接检查本身不会下单。')
    try:combos=eligible()
    except Exception as exc:st.error(f'无法读取组合：{exc}');return
    session=book.session();cfg=session['config'] if session else {}
    running=bool(session and session['status'] not in ('stopped','failed'))
    paper_status()
    with st.expander('交易参数 · 新会话生效',expanded=not running):
        if running:st.info('当前会话保持原参数。停止新增并等已有持仓平仓后，可用新参数启动。')
        with st.form('paper_settings'):
            symbols=st.multiselect('交易标的',list(book.SYMBOLS),default=cfg.get('symbols',['SPX']),disabled=running)
            mode=st.radio('买入方式',['策略自动触发','仅手动买入'],index=0 if cfg.get('auto_trade',True) else 1,horizontal=True,disabled=running)
            strike=st.selectbox('合约选择',['OTM_BUDGET','ATM'],index=0 if cfg.get('strike','OTM_BUDGET')=='OTM_BUDGET' else 1,format_func=lambda x:'价外Call · 按权利金预算（仅SPX）' if x=='OTM_BUDGET' else '最接近平值Call',disabled=running)
            a,b=st.columns(2)
            lower=a.number_input('最低权利金（美元/张）',min_value=1.,max_value=400.,value=float(cfg.get('min_premium',300)),step=10.,disabled=running)
            upper=b.number_input('最高权利金（美元/张，不含手续费）',min_value=1.,max_value=400.,value=float(cfg.get('max_premium',400)),step=10.,disabled=running)
            entry=a.selectbox('买入订单',['LMT','MKT'],index=0 if cfg.get('entry_type','LMT')=='LMT' else 1,disabled=running)
            exit_type=b.selectbox('卖出订单',['MKT','LMT'],index=0 if cfg.get('exit_type','MKT')=='MKT' else 1,disabled=running)
            entry_offset=a.number_input('买入限价偏移（美元/单位）',0.,1.,float(cfg.get('entry_offset',0)),.01,disabled=running)
            exit_offset=b.number_input('卖出限价偏移（美元/单位）',0.,1.,float(cfg.get('exit_offset',0)),.01,disabled=running)
            tif=a.selectbox('买入有效期',['DAY','IOC'],index=0 if cfg.get('tif','DAY')=='DAY' else 1,disabled=running)
            tp_on=b.checkbox('成交后挂止盈单',value=cfg.get('take_profit',.25) is not None,disabled=running)
            tp=b.number_input('止盈涨幅（%）',1.,500.,float((cfg.get('take_profit') or .25)*100),1.,disabled=running)
            sl_on=a.checkbox('启用软件止损',value=cfg.get('stop_loss',.25) is not None,disabled=running)
            sl=a.number_input('止损跌幅（%）',1.,99.,float((cfg.get('stop_loss') or .25)*100),1.,disabled=running)
            min_return=a.number_input('组合最低平均净收益率（%）',10.,1000.,float(cfg.get('filter_return',10)),1.,disabled=running)
            min_trades=b.number_input('组合最少回测笔数',0,100000,int(cfg.get('filter_trades',0)),10,disabled=running)
            st.caption('预算模式仅限SPX、零偏移限价买入；优先选接近最高预算的价外合约。止盈按实际成交权利金涨幅，未扣手续费。每次1张，不重复持仓。')
            submitted=st.form_submit_button('启动 IBKR Paper',disabled=running,type='primary')
            if submitted:
                chosen=[c for c in combos if c['symbol'] in symbols and c['mean_return']>min_return/100 and c['trades']>=min_trades]
                config=dict(symbols=symbols,quantity=1,port=4002,expiry='0DTE',strike=strike,min_premium=lower,target_premium=upper,max_premium=upper,
                    auto_trade=mode=='策略自动触发',entry_type=entry,exit_type=exit_type,entry_offset=entry_offset,exit_offset=exit_offset,tif=tif,
                    take_profit=tp/100 if tp_on else None,stop_loss=sl/100 if sl_on else None,combos=chosen,filter_return=min_return,filter_trades=min_trades)
                try:paper_control.start(config);st.rerun()
                except Exception as exc:st.error(str(exc))
    with st.expander('组合与执行说明'):
        selected=cfg.get('combos',[]) if running else [c for c in combos if c['symbol'] in symbols]
        st.dataframe(pd.DataFrame([{'标的':c['symbol'],'买入':c['buy']['name'],'卖出':c['sell']['name'],'平均净收益率 (%)':round(c['mean_return']*100,2),'胜率 (%)':round(c['win_rate']*100,2),'笔数':c['trades']} for c in selected]),hide_index=True,width='stretch')
        st.caption('排名来自合成平值期权回测，不能直接代表价外期权收益。软件止损、策略退出依赖后台在线；未成交买单15秒后撤销，收盘前1分钟请求退出。')


@st.fragment(run_every='3s')
def paper_status():
    import paper_store as book
    session,trades,events=book.dashboard()
    if not session:st.info('尚未启动Paper交易。');return
    age=(datetime.now(timezone.utc)-datetime.fromisoformat(session['heartbeat'])).total_seconds()
    status=session['status'];healthy=status in ('running','stopping') and age<=90
    if status in ('failed','needs_review') or (status in ('running','starting','stopping') and age>90):st.error(f"需要检查：{session['message']}")
    else:st.write(f"{'🟢' if healthy else '⚪'} {status} · {session['message']}")
    render_profit_history(book)
    c=session['config']
    web_controls=c.get('web_controls',1)>=2
    if not web_controls and status not in ('stopped','failed'):
        st.info('现有持仓由旧会话继续管理。可主动平仓并停止；平仓后启动新会话，即可使用手动买入。')
    st.caption(f"{'自动信号＋手动操作' if c.get('auto_trade',True) else '仅手动买入'} · {', '.join(c['symbols'])} · {'价外预算 $'+str(c.get('max_premium')) if c.get('strike')=='OTM_BUDGET' else '平值Call'} · 止盈 {str(round(c['take_profit']*100,2))+'%' if c.get('take_profit') is not None else '关闭'} · 心跳 {age:.0f}秒前")
    if status in ('starting','running','stopping'):
        a,b=st.columns(2)
        if a.button('停止新增，继续管理持仓',key='paper_stop'):book.control(session['id'],'stop');st.rerun()
        if b.button('全部平仓并停止',key='paper_flatten'):book.control(session['id'],'flatten');st.rerun()
    active=[t for t in trades if t['state'] not in ('closed','cancelled','rejected')]
    for t in active:
        p=t['payload'];symbol=t['symbol']
        with st.container(border=True):
            st.write(f"**{symbol} · {p.get('contract','等待选约')} · {t['state']}**")
            st.caption(p['combo']['buy']['name']+' → '+p['combo']['sell']['name'])
            entry_fills=[f for o in p.get('orders',[]) if o['role']=='entry' for f in o.get('fills',[])]
            if not p.get('entry_price') and entry_fills:
                p['entry_price']=sum(f['price']*f['shares'] for f in entry_fills)/sum(f['shares'] for f in entry_fills)
            a,b,d=st.columns(3)
            a.metric('买入报价 / 单位',f"${p['entry_price']:.2f}" if p.get('entry_price') else '等待成交')
            b.metric('买一报价 / 单位',f"${p['bid']:.2f}" if p.get('bid') is not None else '暂无新鲜报价')
            d.metric('浮动盈亏（未扣手续费）',f"${p['unrealized_gross']:.2f}" if p.get('unrealized_gross') is not None else '—')
            st.caption('提交买入时标的：'+str(p.get('underlying_at_submit','旧记录未采集'))+' · 报价时间：'+str(p.get('quote_time','—')))
            if st.button('主动平仓 1张（按配置卖出）' if web_controls else '主动平仓并停止旧会话',key='close_'+t['id'],disabled=not healthy or t['state']!='open'):
                try:
                    if web_controls:book.enqueue(session['id'],'close',dict(symbol=symbol,trade_id=t['id']))
                    else:book.control(session['id'],'flatten')
                    st.success('平仓请求已发送；成交后更新状态。')
                except ValueError as exc:st.error(str(exc))
    with st.expander('手动买入 1张'):
        choices={x['id']:x for x in c['combos']}
        selected=st.selectbox('买入标的和卖出规则',list(choices),format_func=lambda k:choices[k]['symbol']+' · '+choices[k]['buy']['name']+' → '+choices[k]['sell']['name'],key='manual_combo_'+session['id'])
        st.caption('手动买入不等待买入信号；仍使用本会话的合约预算、止盈止损与所选组合卖出规则。')
        if st.button('立即提交 Paper 买入 1张',type='primary',disabled=not web_controls or not healthy or session['desired']!='run' or not choices):
            try:book.enqueue(session['id'],'buy',dict(symbol=choices[selected]['symbol'],combo_id=selected));st.success('请求已发送；以IBKR成交回报为准。')
            except ValueError as exc:st.error(str(exc))
    commands=book.commands(session['id'])
    if commands:
        st.dataframe(pd.DataFrame(commands)[['created','kind','state','result']].rename(columns={'created':'时间','kind':'操作','state':'状态','result':'处理结果'}),hide_index=True,width='stretch')
    if trades:
        with st.expander('订单与已实现盈亏'):
            st.dataframe(pd.DataFrame([{'时间':t['signal_time'],'标的':t['symbol'],'合约':t['payload'].get('contract',''),'状态':t['state'],'净盈亏 ($)':t['payload'].get('net_profit'),'原因':t['payload'].get('reason','')} for t in trades]),hide_index=True,width='stretch')
            st.json([{'标的':t['symbol'],'订单':t['payload'].get('orders',[])} for t in trades])
    else:st.info('本会话暂无订单。')
    st.write('**运行日志 · 每3秒刷新**')
    if events:st.code('\n'.join(f"{e['time']}  {e['message']}" for e in reversed(events)),language=None)


def render_profit_history(book):
    from zoneinfo import ZoneInfo
    trades=book.history()
    if not trades:return
    def day(t):return datetime.fromisoformat(t['signal_time']).astimezone(ZoneInfo('America/New_York')).date().isoformat()
    days=sorted({day(t) for t in trades},reverse=True)
    selected=st.selectbox('交易日（纽约时间 · 包含当天全部会话）',days,key='paper_profit_day')
    rows=[t for t in trades if day(t)==selected];summary=book.profit_summary(rows)
    a,b,c=st.columns(3)
    a.metric('已实现净盈亏',f"${summary['net']:+.2f}")
    b.metric(f"盈利 {summary['wins']} 笔",f"${summary['profit']:.2f}")
    c.metric(f"亏损 {summary['losses']} 笔",f"-${abs(summary['loss']):.2f}")
    rate=f"{summary['win_rate']:.1%}" if summary['win_rate'] is not None else '—'
    st.caption(f"已平仓 {summary['closed']} 笔 · 胜率 {rate} · 手续费 ${summary['fees']:.2f} · 持平 {summary['flat']} 笔 · 撤单 {summary['cancelled']} 笔。净盈亏已扣手续费，不包含未平仓浮盈亏。")
    if summary['pending']:st.warning(f"{summary['pending']}笔等待手续费确认，暂不计入净盈亏与胜率。")
    display=[]
    for t in rows:
        p=t['payload'];orders=p.get('orders',[])
        def amount(roles):
            fills=[f for o in orders if o['role'] in roles for f in o.get('fills',[])]
            return round(sum(f['price']*f['shares']*100 for f in fills),2) if fills else None
        combo=p.get('combo',{})
        display.append({'信号时间（纽约）':datetime.fromisoformat(t['signal_time']).astimezone(ZoneInfo('America/New_York')).strftime('%H:%M:%S'),
            '标的':t['symbol'],'状态':{'closed':'已平仓','cancelled':'已撤单','open':'持仓中'}.get(t['state'],t['state']),
            '买入金额 ($)':amount(('entry',)),'卖出金额 ($)':amount(('tp','exit')),
            '手续费 ($)':round(p['commission'],2) if p.get('commission') is not None else None,
            '净盈亏 ($)':round(p['net_profit'],2) if p.get('net_profit') is not None else None,
            '买入想法':combo.get('buy',{}).get('name',''),'卖出原因':p.get('reason','')})
    st.dataframe(pd.DataFrame(display),hide_index=True,width='stretch')
