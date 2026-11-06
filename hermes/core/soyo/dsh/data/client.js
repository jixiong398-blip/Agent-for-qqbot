// SPDX-License-Identifier: MIT
// Native supporting panes and navigation, never a second chat/composer.
window.__ModuleLoader__.load({ id: '@soyo/dsh-data', factory: require => {
  const React = require('react'), h = React.createElement;
  return { inject: ['slots', 'sidebarRightTabs', 'sidebarRight', 'connection', 'sessions', 'conversation', 'uiWorkspace'],
    apply(ctx) {
      const rpc = async (service, method, args = {}) => {
        const result = await ctx.connection.rpc.call('/api', service + '/' + method, { args });
        if (!result.ok) throw Error('原生数据接口暂不可用，请稍后刷新。');
        return result.value;
      };
      const paneStyle = { padding: 12, overflowY: 'auto', height: '100%', boxSizing: 'border-box' };
      const select = (label, value, options, change) => h('label', null, label, h('select', { value,
        style: { display: 'block', width: '100%', margin: '6px 0', padding: 6 }, onChange: event => change(event.target.value) },
        ...options.map(([id, text]) => h('option', { key: id, value: id }, text))));
      const kinds = { messages: '群聊 / 私聊原话', events: '平台事件', facts: '场景与共享记忆', turns: '回合与经历',
        actions: '行动脑报告', scene_notes: '跨会话便签', state: '自我状态', people: '对人的认识', emotions: '情感与挂账',
        qzone: 'Qzone 发布账', legacy: '旧私有记忆（只读）', deliveries: '发送与回执' };
      function Data(props) {
        const visible = props.useTabInfo().tab.visible;
        const [catalog, setCatalog] = React.useState(null), [scene, setScene] = React.useState('');
        const [category, setCategory] = React.useState('messages'), [search, setSearch] = React.useState('');
        const [offset, setOffset] = React.useState(0), [page, setPage] = React.useState(null), [error, setError] = React.useState('');
        const [refresh, setRefresh] = React.useState(0);
        React.useEffect(() => {
          if (!visible) return;
          let live = true;
          rpc('soyoData', 'catalog').then(value => { if (!live) return; setCatalog(value);
            setScene(old => value.scenes.some(row => row.session_id === props.sessionId) ? props.sessionId :
              value.scenes.some(row => row.session_id === old) ? old : value.scenes[0]?.session_id ?? '');
          }).catch(error => { if (live) setError(error.message); });
          return () => { live = false; };
        }, [visible, props.sessionId, refresh]);
        React.useEffect(() => {
          if (!visible || !scene) return;
          let live = true; setError(''); setPage(null);
          const timer = setTimeout(() => rpc('soyoData', 'memory', { request: { session_id: scene, category, offset, search } })
            .then(value => { if (live) setPage(value); }).catch(error => { if (live) setError(error.message); }), 200);
          return () => { live = false; clearTimeout(timer); };
        }, [visible, scene, category, offset, search, refresh]);
        const change = setter => value => { setter(value); setOffset(0); };
        return h('section', { 'aria-label': 'Soyo 记忆与数据', style: paneStyle },
          h('h3', null, 'Soyo · 记忆与数据'),
          h('p', null, '只读查看，不调用模型。QQ群只在明确 @ 后推理，未 @ 原话仍保留。'),
          select('会话', scene, (catalog?.scenes ?? []).map(row => [row.session_id, (row.message_type === 'group' ? '群聊 · ' : '私聊 · ') + row.name]), change(setScene)),
          select('数据类型', category, Object.entries(kinds), change(setCategory)),
          h('input', { 'aria-label': '搜索当前场景数据', placeholder: '搜索当前场景', value: search, maxLength: 160,
            style: { width: '100%', boxSizing: 'border-box', padding: 6 }, onChange: event => change(setSearch)(event.target.value) }),
          h('button', { onClick: () => setRefresh(value => value + 1), style: { margin: '8px 0' } }, '刷新'),
          catalog?.collaborator.configured && h('p', null, '协作者：GPT · ' + catalog.collaborator.model),
          catalog?.schedules?.length > 0 && h('details', null, h('summary', null, '自动化任务 ' + catalog.schedules.length + ' 条'),
            ...catalog.schedules.map(task => h('p', { key: task.id }, task.title + ' · ' + task.kind + ' · ' + task.scheduledAt))),
          error && h('p', { role: 'alert' }, error),
          !catalog?.scenes.length && h('p', null, '等待真实 QQ 渠道目录；测试会话不列入这里。'),
          page?.note && h('p', null, page.note),
          ...((page?.rows ?? []).map(row => h('details', { key: row.id, style: { padding: '8px 0', borderBottom: '1px solid #8884' } },
            h('summary', null, row.title, row.occurred_at ? ' · ' + new Date(row.occurred_at * 1000).toLocaleString() : ''),
            h('p', { style: { whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' } }, row.text || '（无文本 / 仅媒体记录）'),
            row.state && h('small', null, row.state), row.note && h('p', null, row.note)))),
          page && !page.rows.length && h('p', null, '当前范围暂无匹配记录。'),
          h('div', { style: { display: 'flex', gap: 8, marginTop: 10 } },
            h('button', { disabled: !offset, onClick: () => setOffset(Math.max(0, offset - 24)) }, '上一页'),
            h('button', { disabled: !page || page.next_offset === null, onClick: () => setOffset(page.next_offset) }, '下一页')));
      }
      const states = { starting: '准备', running: '工作中', completed: '行动回合已结束', failed: '失败', paused: '暂停' };
      const handovers = { pending: '报告待交回', ready_for_character: '报告已就绪 · 角色尚未读', character_read: '角色已读',
        no_report: '没有完成报告', handback_deferred: '报告回流待处理', handback_failed: '角色读取未完成' };
      const openAction = async task => {
        const address = await rpc('soyoBrains', 'reveal', { request: { id: task.id } });
        await ctx.uiWorkspace.openSession(address);
      };
      function Brains(props) {
        const visible = props.useTabInfo().tab.visible;
        const [value, setValue] = React.useState(null), [error, setError] = React.useState(''), [all, setAll] = React.useState(true);
        React.useEffect(() => {
          if (!visible) return;
          let live = true, busy = false;
          const refresh = async () => {
            if (busy) return; busy = true;
            try {
              const value = await rpc('soyoBrains', all ? 'catalog' : 'list', all ? {} : { request: { session_id: props.sessionId } });
              if (live) { setValue(value); setError(''); }
            } catch (error) { if (live) setError(error.message); }
            finally { busy = false; }
          };
          refresh(); const timer = setInterval(refresh, 3000);
          return () => { live = false; clearInterval(timer); };
        }, [visible, props.sessionId, all]);
        return h('section', { 'aria-label': 'Soyo 双脑区', style: paneStyle },
          h('h3', null, 'Soyo · 双脑区'),
          h('p', null, '角色脑：Soyo · 行动脑：独立原生子会话 · GPT：辅助脑。查看不会调用模型。'),
          h('label', null, h('input', { type: 'checkbox', checked: all, onChange: event => setAll(event.target.checked) }), '全部行动任务（含其他父会话）'),
          error && h('p', { role: 'alert' }, error),
          value && !value.tasks.length && h('p', null, '当前范围没有行动任务；可切换到全部。'),
          ...(value?.tasks ?? []).map(task => h('article', { key: task.id, style: { margin: '12px 0', padding: 10, border: '1px solid #8885', borderRadius: 8 } },
            h('strong', null, task.objective),
            h('p', null, (states[task.state] ?? task.state) + ' · ' + (handovers[task.handover] ?? task.handover)),
            h('small', null, '父会话：' + task.parent_session),
            task.native_observations && h('p', null, '模型步骤 ' + task.native_observations.model_steps + ' · 工具调用 ' + task.native_observations.tool_calls + ' / 回执 ' + task.native_observations.tool_results),
            task.native_address ? h('button', { onClick: () => openAction(task).catch(error => setError(error.message)) }, '打开原生行动会话') :
              h('small', null, '旧任务缺少原生父子地址，仅保留审计报告。'),
            h('details', null, h('summary', null, '双脑协作线程 · 工具证据 ' + task.evidence.length + ' 条'),
              ...task.thread.map((message, index) => h('p', { key: index, style: { whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' } },
                (message.speaker === 'character' ? '角色：' : message.speaker === 'action_question' ? '行动提问：' : '行动：') + message.text)),
              ...task.evidence.map((item, index) => h('p', { key: 'e' + index }, item.operation + ' · ' + item.state + (item.commit ? ' · ' + item.commit : '')))))));
      }
      function ActionEntries({ wide }) {
        const authorUi = ctx.slots.entries('conversation.chat.node').some(entry => entry.options.key === 'asuna-stage');
        const [tasks, setTasks] = React.useState([]), [error, setError] = React.useState('');
        React.useEffect(() => {
          if (!wide || authorUi) return;
          let live = true, busy = false;
          const refresh = async () => {
            if (busy) return; busy = true;
            try { const value = await rpc('soyoBrains', 'catalog'); if (live) { setTasks(value.tasks); setError(''); } }
            catch (error) { if (live) setError(error.message); }
            finally { busy = false; }
          };
          refresh(); const timer = setInterval(refresh, 5000);
          return () => { live = false; clearInterval(timer); };
        }, [wide, authorUi]);
        if (authorUi) return null; // Author header/tabs own primary navigation now.
        if (!wide) return null;
        return h('section', { 'aria-label': 'Soyo 行动会话入口', style: { width: '100%', padding: '6px 4px', boxSizing: 'border-box' } },
          h('div', { style: { display: 'flex', gap: 8, marginBottom: 6 } },
            h('button', { onClick: () => ctx.sidebarRight.openTab('soyo-brains') }, '双脑区'),
            h('button', { onClick: () => ctx.sidebarRight.openTab('soyo-notes') }, '跨会话便签')),
          h('details', null, h('summary', { style: { cursor: 'pointer' } }, '行动脑会话 · ' + tasks.length),
            h('small', null, '原生子会话由独立入口展示，普通会话列表不会列出它们。'),
            h('div', { style: { maxHeight: 190, overflowY: 'auto' } }, ...tasks.slice(0, 12).map(task => h('button', {
              key: task.id, disabled: !task.native_address, title: task.objective, 'aria-label': '行动会话 ' + task.id,
              onClick: () => openAction(task).catch(error => setError(error.message)),
              style: { display: 'block', width: '100%', textAlign: 'left', padding: 6, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
            }, (states[task.state] ?? task.state) + ' · ' + task.objective.slice(0, 45)))),
            error && h('p', { role: 'alert' }, error)));
      }
      const noteStates = { waiting: '送到了，还没读', offered: '本轮展示，尚未结算已读', read: '读了，没回', replied: '读了，回了', expired: '过期（原记录保留）' };
      function Notes(props) {
        const visible = props.useTabInfo().tab.visible;
        const [places, setPlaces] = React.useState([]), [place, setPlace] = React.useState('');
        const [page, setPage] = React.useState(null), [error, setError] = React.useState(''), [offset, setOffset] = React.useState(0);
        const [refresh, setRefresh] = React.useState(0);
        React.useEffect(() => {
          if (!visible) return;
          let live = true;
          rpc('soyoNotes', 'catalog').then(value => {
            if (!live) return; setPlaces(value.places);
            setPlace(old => value.places.find(row => row.session_id === props.sessionId)?.place || old || value.places[0]?.place || '');
          }).catch(error => { if (live) setError(error.message); });
          return () => { live = false; };
        }, [visible, props.sessionId, refresh]);
        React.useEffect(() => {
          if (!visible || !place) return;
          let live = true; setError('');
          rpc('soyoNotes', 'page', { request: { place, offset } }).then(value => { if (live) setPage(value); })
            .catch(error => { if (live) setError(error.message); });
          return () => { live = false; };
        }, [visible, place, offset, refresh]);
        return h('section', { 'aria-label': 'Soyo 跨会话便签', style: paneStyle },
          h('h3', null, 'Soyo · 跨会话便签'),
          h('p', null, '是 Soyo 写给别的会话里的自己的话，不是平台消息。next_time 不主动唤醒；QQ群等下次明确 @。'),
          select('便签会话', place, places.map(row => [row.place, row.name]), value => { setPlace(value); setOffset(0); }),
          h('button', { onClick: () => setRefresh(value => value + 1) }, '刷新便签'),
          error && h('p', { role: 'alert' }, error),
          page && !page.rows.length && h('p', null, '当前会话还没有跨会话便签。'),
          ...(page?.rows ?? []).map(row => h('details', { key: row.id, style: { padding: '8px 0', borderBottom: '1px solid #8884' } },
            h('summary', null, row.title + ' · ' + (noteStates[row.state] ?? row.state)),
            h('p', { style: { whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' } }, row.text),
            h('small', null, row.mode + ' · ' + row.id),
            row.read_at && h('p', null, '读取回合已完成：' + new Date(row.read_at).toLocaleString()),
            row.reply_to && h('p', null, '回信给：' + row.reply_to), row.reply_note_id && h('p', null, '收到回信：' + row.reply_note_id))),
          h('button', { disabled: !offset, onClick: () => setOffset(Math.max(0, offset - 24)) }, '上一页'),
          h('button', { disabled: !page || page.next_offset === null, onClick: () => setOffset(page.next_offset) }, '下一页'));
      }
      for (const [id, kind, title, description, component, order] of [
        ['data', 'soyo-data', '记忆与数据', '场景原话、记忆与真实发送回执', Data, 60],
        ['brains', 'soyo-brains', '双脑区', '全部行动任务、工具证据和原生子会话入口', Brains, 61],
        ['notes', 'soyo-notes', '跨会话便签', '来源、next_time/wake、已读和回信', Notes, 62],
      ]) {
        ctx.effect(() => ctx.sidebarRightTabs.register({ id: '@soyo/' + id, kind, title: () => title,
          guide: [{ id: 'soyo-' + id, order, title: () => title, description: () => description }] }));
        ctx.slots.inject('sidebar.right.pane.tab', () => ctx.slots.register({ name: 'sidebar.right.pane.tab', key: '@soyo/' + id }, component));
      }
      ctx.slots.inject('sidebar.footer.action', () => ctx.slots.register({ name: 'sidebar.footer.action', id: 'soyo-action-sessions', order: 290 }, ActionEntries));
      const blocks = new Map();
      const update = () => {
        for (const id of Object.keys(ctx.sessions.list.getSnapshot().byId)) {
          if (!id.startsWith('soyo-qq-') && !id.startsWith('soyo-consult-') && !id.startsWith('soyo-agent-line-') && !id.startsWith('soyo-action-')) continue;
          if (blocks.has(id)) continue;
          const block = { reason: '外部 QQ / 协作记录只读；请在原渠道回应，不从此处冒充发送人。' };
          blocks.set(id, block); ctx.conversation.blocks.set(id, block);
        }
      };
      ctx.effect(() => { const unsubscribe = ctx.sessions.list.subscribe(update); update();
        return () => { unsubscribe(); for (const [id, block] of blocks) if (ctx.conversation.blocks.storeFor(id).getSnapshot() === block) ctx.conversation.blocks.set(id, undefined); }; });
    } };
} });
