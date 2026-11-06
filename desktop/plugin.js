/**
 * hermesmade: add community bots from hermesmade.lol, share your own.
 *
 * hermes://open/hermesmade?add=<id>  -> this page, Add tab, preloaded with the bot.
 * hermes://open/hermesmade?tab=grok  -> the Grok Bot migration steps.
 * Nothing installs or uploads without an explicit click here. Backend lives in
 * the same package: dashboard/plugin_api.py -> /api/plugins/hermesmade/*.
 *
 * No hardcoded colours: theme vars only. One import surface: @hermes/plugin-sdk.
 */
import * as sdk from '@hermes/plugin-sdk'
import { useEffect, useState } from 'react'
import { jsx, jsxs } from 'react/jsx-runtime'

const ROUTE = '/hermesmade'
const SITE = 'https://hermesmade.lol'
const { host, ROUTES_AREA, SIDEBAR_NAV_AREA, PALETTE_AREA, Button, Input, Textarea, GlyphSpinner, queryClient } = sdk

let CTX = null

const c = {
  primary: 'var(--ui-text-primary)',
  secondary: 'var(--ui-text-secondary)',
  tertiary: 'var(--ui-text-tertiary)',
  quaternary: 'var(--ui-text-quaternary)',
  stroke: 'var(--ui-stroke-secondary)',
  accent: 'var(--ui-accent)',
  red: 'var(--ui-red)',
  green: 'var(--ui-green)',
  yellow: 'var(--ui-yellow)'
}

const FRIENDLY = [
  [/no Grok Bot export found/i, "That isn't a Grok Bot export yet. Paste the Bot's whole reply to the export prompt (the part with the JSON), or choose the file it saved."],
  [/looks cut off/i, 'That export looks cut off. Ask the Bot to send the rest, then paste every part here.'],
  [/credential-looking keys/i, 'That export contains something that looks like a key or password, so it was not read. Ask the Bot to export again and leave keys out.'],
  [/Bot not found|HTTP 404|^Not Found$/i, "That bot isn't on hermesmade.lol (it may have been removed). Browse the shelf for another."],
  [/no name yet/i, 'Give this bot a title first (the box below), so people know what it is.'],
  [/Give a bot id/i, 'Paste a bot link from hermesmade.lol/bots, or its number.'],
  [/handle is required/i, 'Add your @handle (letters, digits or underscore) so people know who made it.'],
  [/Failed to fetch|ECONNREFUSED|timed out|URLError|Name or service/i, "Couldn't reach hermesmade.lol. Check your connection and try again."]
]

const errText = e => {
  let m = (e && (e.detail || e.message)) || String(e)
  // "Error invoking remote method 'hermes:api': Error: 400: {"detail": "..."}" -> the detail.
  m = m.replace(/^Error invoking remote method '[^']+':\s*/, '').replace(/^Error:\s*/, '').replace(/^\d{3}:\s*/, '')

  try {
    const j = JSON.parse(m)

    m = (j && (j.detail || j.error)) || m
  } catch {
    /* plain text */
  }

  m = String(m)
  const hit = FRIENDLY.find(([rx]) => rx.test(m))

  return hit ? hit[1] : m.charAt(0).toUpperCase() + m.slice(1)
}

// The plugin's backend lives in the profile it was installed into (your main one). When a bot is
// the active profile, its backend has no hermesmade and answers "Plugin not found", so say that
// plainly and offer the switch instead of a raw 404 on every button.
const MAIN_PROFILE = 'default'
let onWrongProfile = null

async function rest(path, opts) {
  try {
    return await CTX.rest(path, opts)
  } catch (e) {
    const m = String((e && (e.detail || e.message)) || e)
    if (/Plugin not found/i.test(m)) {
      onWrongProfile?.(host.state.profile.get())
      throw new Error('Community bots runs on your main Hermes profile. Switch back to it to continue.')
    }
    throw e
  }
}

function switchToMain() {
  const back = (window.location.hash || '').replace(/^#/, '') || ROUTE
  host.newChat(MAIN_PROFILE)
  setTimeout(() => host.navigate(back.startsWith(ROUTE) ? back : ROUTE), 600)
}

function readQuery() {
  const h = window.location.hash || ''
  const q = h.includes('?') ? h.slice(h.indexOf('?') + 1) : ''

  return new URLSearchParams(q)
}

const box = { border: `1px solid ${c.stroke}`, borderRadius: 10, padding: 16 }
const label = { fontSize: 11, letterSpacing: '0.08em', textTransform: 'uppercase', color: c.tertiary, margin: '0 0 6px' }

function Section({ title, children }) {
  return jsxs('div', { style: { minWidth: 0 }, children: [jsx('p', { style: label, children: title }), children] })
}

function List({ items, empty }) {
  if (!items || !items.length) {
    return jsx('p', { style: { margin: 0, color: c.quaternary, fontSize: 13 }, children: empty })
  }

  return jsx('ul', {
    style: { margin: 0, paddingLeft: 18, display: 'grid', gap: 4, fontSize: 13, color: c.secondary },
    children: items.map((t, i) => jsx('li', { style: { overflowWrap: 'anywhere' }, children: t }, i))
  })
}

// ------------------------------------------------------------------- add --
function AddPane({ initial }) {
  const [ref, setRef] = useState(initial || '')
  const [state, setState] = useState({ phase: initial ? 'loading' : 'idle' })

  const load = async id => {
    if (!id) {
      return
    }

    setState({ phase: 'loading' })

    try {
      const pv = await rest(`/preview?bot=${encodeURIComponent(id)}`)
      setState({ phase: 'preview', pv, name: pv.install_as })
    } catch (e) {
      setState({ phase: 'error', error: errText(e) })
    }
  }

  useEffect(() => {
    if (initial) {
      setRef(initial)
      void load(initial)
    }
  }, [initial])

  const doInstall = async () => {
    setState(s => ({ ...s, phase: 'installing' }))

    try {
      const out = await rest('/install', { method: 'POST', body: { bot: ref, name: state.name }, timeoutMs: 180000 })
      setState(s => ({ ...s, phase: 'done', out }))
      sdk.haptic?.('success')
      host.notify({ kind: 'success', message: `Added ${out.title || out.profile}` })
      // Refresh the bot roster so the new bot appears without a reload.
      queryClient?.invalidateQueries?.({ queryKey: ['hermes-bots'] })
    } catch (e) {
      setState(s => ({ ...s, phase: 'preview', error: errText(e) }))
    }
  }

  const pv = state.pv
  const b = pv && pv.bot
  const m = (b && b.meta) || {}

  return jsxs('div', {
    style: { display: 'grid', gap: 16 },
    children: [
      jsxs('form', {
        style: { display: 'flex', gap: 8 },
        onSubmit: e => {
          e.preventDefault()
          void load(ref.trim())
        },
        children: [
          jsx(Input, { value: ref, placeholder: 'Bot id or hermesmade.lol/bots/… link', onChange: e => setRef(e.target.value), style: { flex: 1 } }),
          jsx(Button, { type: 'submit', variant: 'secondary', children: 'Look up' }),
          jsx(Button, { type: 'button', variant: 'ghost', onClick: () => CTX.os.openExternal(`${SITE}/bots`), children: 'Browse bots' })
        ]
      }),
      state.phase === 'loading' && jsxs('div', { style: { display: 'flex', gap: 8, alignItems: 'center', color: c.secondary }, children: [jsx(GlyphSpinner, {}), 'Downloading and scanning…'] }),
      state.phase === 'error' && jsx('p', { style: { color: c.red, margin: 0 }, children: state.error }),
      b &&
        jsxs('div', {
          style: { ...box, display: 'grid', gap: 18 },
          children: [
            jsxs('div', {
              children: [
                jsx('h2', { style: { margin: 0, fontSize: 22, color: c.primary }, children: b.title }),
                jsx('p', { style: { margin: '4px 0 0', color: c.secondary }, children: `${b.tagline || ''}` }),
                jsx('p', { style: { margin: '6px 0 0', color: c.tertiary, fontSize: 12 }, children: `by ${b.owner_handle} · v${b.version} · ${b.installs} installs` })
              ]
            }),
            jsxs('div', {
              style: { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 16 },
              children: [
                jsx(Section, { title: 'Skills', children: jsx(List, { items: m.skills, empty: 'Built-in skills only' }) }),
                jsx(Section, { title: 'Schedules (arrive paused)', children: jsx(List, { items: (m.cron || []).map(j => `${j.name}  ${j.schedule || ''}`), empty: 'None' }) }),
                jsx(Section, { title: 'MCP (arrive off)', children: jsx(List, { items: (m.mcp || []).map(x => x.name), empty: 'None' }) }),
                jsx(Section, { title: 'Keys it can use', children: jsx(List, { items: (m.env_requires || []).map(e => e.name), empty: 'Your normal model login' }) })
              ]
            }),
            jsx(Section, {
              title: 'Safety scan',
              children: jsx(List, {
                items: pv.scans.map(s => `${s.skill}: ${s.verdict}${s.findings.length ? ` (${s.findings.slice(0, 2).join('; ')})` : ''}`),
                empty: 'No skills to scan'
              })
            }),
            jsx(Section, {
              title: 'Personality (SOUL.md)',
              children: jsx('pre', {
                style: { margin: 0, maxHeight: 220, overflow: 'auto', whiteSpace: 'pre-wrap', fontSize: 12, color: c.secondary, fontFamily: 'var(--font-mono, ui-monospace)' },
                children: pv.soul
              })
            }),
            state.phase !== 'done' &&
              jsxs('div', {
                style: { display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' },
                children: [
                  jsx('span', { style: { color: c.tertiary, fontSize: 13 }, children: 'Install as' }),
                  jsx(Input, { value: state.name || '', onChange: e => setState(s => ({ ...s, name: e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, '-') })), style: { width: 200 } }),
                  jsx(Button, {
                    disabled: pv.blocked || state.phase === 'installing',
                    onClick: doInstall,
                    children: state.phase === 'installing' ? 'Adding…' : pv.blocked ? 'Blocked by scanner' : 'Add bot'
                  })
                ]
              }),
            state.error && state.phase !== 'error' && jsx('p', { style: { color: c.red, margin: 0 }, children: state.error }),
            state.phase === 'done' &&
              jsxs('div', {
                style: { display: 'grid', gap: 6 },
                children: [
                  jsx('p', { style: { margin: 0, color: c.green }, children: `Added as “${state.out.profile}”. It's in your bot list now.` }),
                  jsxs('div', { style: { display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 4 }, children: [
                    jsx(Button, { onClick: () => host.newChat(state.out.profile), children: `Chat with ${state.out.title || state.out.profile}` }),
                    jsx(Button, { variant: 'ghost', onClick: () => CTX.os.openExternal(`${SITE}/bots`), children: 'Find another bot' })
                  ] }),
                  state.out.cron_paused > 0 && jsx('p', { style: { margin: 0, color: c.secondary, fontSize: 13 }, children: `${state.out.cron_paused} schedule(s) are paused. Turn them on from that bot's Cron tab when you're ready.` }),
                  state.out.mcp_disabled.length > 0 && jsx('p', { style: { margin: 0, color: c.secondary, fontSize: 13 }, children: `MCP servers off: ${state.out.mcp_disabled.join(', ')}.` })
                ]
              })
          ]
        })
    ]
  })
}

// ----------------------------------------------------------------- share --
function SharePane() {
  const [profiles, setProfiles] = useState([])
  const [form, setForm] = useState({ profile: '', title: '', handle: '', tagline: '', description: '' })
  const [st, setSt] = useState({ phase: 'idle' })

  useEffect(() => {
    rest('/profiles').then(r => setProfiles(r.profiles || [])).catch(() => {})
    const h = CTX.storage.get('handle', '')

    if (h) {
      setForm(f => ({ ...f, handle: h }))
    }
  }, [])

  const set = k => e => setForm(f => ({ ...f, [k]: e.target.value }))

  const preview = async () => {
    setSt({ phase: 'packing' })

    try {
      setSt({ phase: 'preview', plan: await rest('/pack', { method: 'POST', body: form, timeoutMs: 120000 }) })
    } catch (e) {
      setSt({ phase: 'error', error: errText(e) })
    }
  }

  const share = async () => {
    setSt(s => ({ ...s, phase: 'uploading' }))

    try {
      CTX.storage.set('handle', form.handle)
      const res = await rest('/share', { method: 'POST', body: form, timeoutMs: 120000 })
      setSt(s => ({ ...s, phase: 'done', res }))
      host.notify({ kind: 'success', message: 'Bot shared. It goes live after review.' })
    } catch (e) {
      setSt(s => ({ ...s, phase: 'preview', error: errText(e) }))
    }
  }

  const p = st.plan

  return jsxs('div', {
    style: { display: 'grid', gap: 14, maxWidth: 720 },
    children: [
      jsxs('label', {
        style: { display: 'grid', gap: 6 },
        children: [
          jsx('span', { style: label, children: 'Bot to share' }),
          jsx('select', {
            value: form.profile,
            onChange: set('profile'),
            style: { padding: '8px 10px', borderRadius: 8, border: `1px solid ${c.stroke}`, background: 'transparent', color: c.primary },
            children: [jsx('option', { value: '', children: 'Active bot' }, ''), ...profiles.map(r => jsx('option', { value: r.name, children: r.title }, r.name))]
          })
        ]
      }),
      jsx(Input, { placeholder: 'Bot title shown on hermesmade.lol (needed if this is your main bot)', value: form.title, onChange: set('title') }),
      jsx(Input, { placeholder: 'Your @handle (X or GitHub)', value: form.handle, onChange: set('handle') }),
      jsx(Input, { placeholder: 'One-line tagline', value: form.tagline, onChange: set('tagline') }),
      jsx(Textarea, { placeholder: 'What does it do? Who is it for?', value: form.description, onChange: set('description'), rows: 3 }),
      jsxs('div', {
        style: { display: 'flex', gap: 8 },
        children: [
          jsx(Button, { variant: 'secondary', onClick: preview, disabled: st.phase === 'packing', children: st.phase === 'packing' ? 'Building…' : 'Preview package' }),
          p && st.phase !== 'done' && jsx(Button, { onClick: share, disabled: !form.handle.trim() || st.phase === 'uploading', children: st.phase === 'uploading' ? 'Sharing…' : 'Share to hermesmade.lol' }),
          p && st.phase !== 'done' && !form.handle.trim() && jsx('span', { style: { color: c.tertiary, fontSize: 12, alignSelf: 'center' }, children: 'Add your @handle to share' })
        ]
      }),
      st.phase === 'error' && jsx('p', { style: { color: c.red, margin: 0 }, children: st.error }),
      p &&
        jsxs('div', {
          style: { ...box, display: 'grid', gap: 12 },
          children: [
            jsx('p', { style: { margin: 0, color: c.primary }, children: `${p.title} · v${p.version} · ${Math.max(1, Math.round(p.bytes / 1024))} KB${p.update_of ? ` · updates listing #${p.update_of}` : ''}` }),
            jsx(Section, { title: 'Exactly what ships', children: jsx(List, { items: p.files, empty: '' }) }),
            jsx('p', { style: { margin: 0, fontSize: 13, color: c.tertiary }, children: 'Never ships: .env, auth.json, API keys, bot tokens, memories, sessions, chat history, your model login.' }),
            p.warnings.length > 0 && jsx(Section, { title: 'Notes', children: jsx(List, { items: p.warnings, empty: '' }) }),
            st.error && jsx('p', { style: { color: c.red, margin: 0 }, children: st.error })
          ]
        }),
      st.phase === 'done' &&
        jsxs('div', {
          style: { display: 'grid', gap: 8 },
          children: [
            jsx('p', { style: { margin: 0, color: c.green }, children: st.res.message }),
            jsxs('div', { style: { display: 'flex', gap: 8, flexWrap: 'wrap' }, children: [
              jsx(Button, { onClick: () => CTX.os.openExternal(st.res.url), children: 'View the listing' }),
              jsx(Button, { variant: 'ghost', onClick: () => CTX.os.writeClipboard(st.res.url).then(ok => ok && host.notify({ kind: 'success', message: 'Link copied' })), children: 'Copy link' })
            ] })
          ]
        })
    ]
  })
}

// ------------------------------------------------------------- grok bot --
// Grok Bot keeps bots in xAI's cloud with no export button, so each Bot exports itself:
// copy the prompt, open Grok Bot, paste it in the Bot's chat, bring the reply back here.
// The official agent-importers plugin does the reading; nothing here talks to xAI.
// x.ai's own "Open Grok Bot" handoff page (it launches grokbot://app/v1/open, or offers the download).
const GROK_OPEN_WEB = 'https://x.ai/bot/link/v1/open'

const CHECK = jsx('svg', { viewBox: '0 0 24 24', width: 14, height: 14, fill: 'none', stroke: 'currentColor', strokeWidth: 2, strokeLinecap: 'round', strokeLinejoin: 'round', 'aria-label': 'done', children: jsx('path', { d: 'm5 12.5 4.2 4.2L19 7' }) })

function Step({ n, title, children, done }) {
  return jsxs('div', {
    style: { ...box, display: 'grid', gridTemplateColumns: '28px minmax(0,1fr)', gap: 12, opacity: done ? 0.7 : 1 },
    children: [
      jsx('span', { style: { fontFamily: 'var(--font-mono, ui-monospace)', fontSize: 12, color: done ? c.green : c.accent, paddingTop: 2 }, children: done ? CHECK : String(n).padStart(2, '0') }),
      jsxs('div', { style: { display: 'grid', gap: 10, minWidth: 0 }, children: [jsx('p', { style: { margin: 0, color: c.primary, fontWeight: 600 }, children: title }), children] })
    ]
  })
}

function GrokPane() {
  const [prompt, setPrompt] = useState('')
  const [copied, setCopied] = useState(false)
  const [opened, setOpened] = useState(false)
  const [text, setText] = useState('')
  const [files, setFiles] = useState([])
  const [scan, setScan] = useState({ phase: 'idle' })
  const [st, setSt] = useState({ phase: 'idle' })
  const [names, setNames] = useState({})
  const [skip, setSkip] = useState({})
  const [importer, setImporter] = useState({ phase: 'checking' })

  const scanDownloads = async quiet => {
    setScan({ phase: 'scanning' })
    try {
      const d = await rest('/grok/downloads')
      const found = d.files || []
      setFiles(found)
      setScan({ phase: 'done', n: found.length, quiet })
      return found
    } catch (e) {
      setScan({ phase: 'done', n: 0, error: errText(e) })
      return []
    }
  }

  const applyStatus = r => {
    setImporter({ phase: r.importer ? 'ready' : 'missing', hint: r.install_hint })
    setPrompt(r.prompt || '')
    if (r.importer) {
      void scanDownloads(true)
    }
  }

  useEffect(() => {
    rest('/grok/status')
      .then(applyStatus)
      .catch(e => setImporter({ phase: 'error', error: errText(e) }))
  }, [])

  // Coming back from Grok Bot: look in Downloads again on its own, so the user never has to.
  useEffect(() => {
    if (!opened) {
      return
    }
    const onFocus = () => void scanDownloads(true)
    window.addEventListener('focus', onFocus)
    const timer = setInterval(() => {
      if (!document.hidden) {
        void scanDownloads(true)
      }
    }, 5000)
    return () => {
      window.removeEventListener('focus', onFocus)
      clearInterval(timer)
    }
  }, [opened])

  const installImporter = async () => {
    setImporter(s => ({ ...s, phase: 'installing' }))
    try {
      applyStatus(await rest('/grok/install-importer', { method: 'POST', timeoutMs: 300000 }))
    } catch (e) {
      setImporter(s => ({ ...s, phase: 'missing', error: errText(e) }))
    }
  }

  const copy = async () => {
    const ok = (await CTX.os.writeClipboard(prompt)) || (await navigator.clipboard?.writeText(prompt).then(() => true, () => false))
    if (ok) {
      setCopied(true)
      setTimeout(() => setCopied(false), 1800)
    } else {
      host.notify({ kind: 'error', message: 'Could not copy. Select the prompt text and copy it yourself.' })
    }
    return ok
  }

  // One click: copy the prompt AND open Grok Bot, so the paste is ready when it opens.
  const openGrok = async () => {
    await copy()
    setOpened(true)
    const ok = await CTX.os.openExternal(GROK_OPEN_WEB)
    host.notify({
      kind: ok ? 'success' : 'error',
      message: ok
        ? 'Prompt copied. Paste it into a Bot in Grok Bot, send, then come back here.'
        : `Could not open your browser. Go to ${GROK_OPEN_WEB} yourself; the prompt is copied.`
    })
  }

  const chooseFile = async () => {
    const path = await CTX.os.pickOpenPath({ title: 'Choose a Grok Bot export', filters: [{ name: 'Grok Bot export', extensions: ['json', 'md', 'txt'] }] })
    if (path) {
      setText('')
      setFiles(f => (f.includes(path) ? f : [...f, path]))
      setScan({ phase: 'done', n: 1, picked: true })
    }
  }

  const source = () => (text.trim() ? { text } : { files })

  const check = async () => {
    setSt({ phase: 'reading' })
    try {
      const pv = await rest('/grok/preview', { method: 'POST', body: source(), timeoutMs: 120000 })
      setNames(Object.fromEntries(pv.bots.map(b => [b.name, b.profile])))
      setSkip({})
      setSt({ phase: 'preview', pv })
    } catch (e) {
      setSt({ phase: 'error', error: errText(e) })
    }
  }

  const run = async () => {
    const pv = st.pv
    const only = pv.bots.filter(b => !skip[b.name]).map(b => b.name)
    setSt(s => ({ ...s, phase: 'migrating', error: null }))
    try {
      const out = await rest('/grok/migrate', {
        method: 'POST',
        body: { ...source(), only, names: Object.fromEntries(pv.bots.filter(b => !b.existing).map(b => [b.name, names[b.name]])) },
        timeoutMs: 300000
      })
      setSt(s => ({ ...s, phase: 'done', out }))
      sdk.haptic?.('success')
      host.notify({ kind: 'success', message: `Moved ${out.results.length} bot${out.results.length === 1 ? '' : 's'} from Grok Bot` })
      queryClient?.invalidateQueries?.({ queryKey: ['hermes-bots'] })
    } catch (e) {
      setSt(s => ({ ...s, phase: 'preview', error: errText(e) }))
    }
  }

  const pv = st.pv
  const haveText = Boolean(text.trim())
  const haveInput = haveText || files.length > 0

  if (importer.phase !== 'ready') {
    return jsxs('div', {
      style: { ...box, display: 'grid', gap: 10, maxWidth: 640 },
      children: [
        jsx('p', { style: { margin: 0, color: c.primary, fontWeight: 600 }, children: 'One-time setup' }),
        jsx('p', { style: { margin: 0, color: c.secondary, fontSize: 13 }, children: 'Reading Grok Bot exports is done by agent-importers, the official Nous importer from the Hermes plugin catalog. Install it once to continue.' }),
        importer.phase === 'checking'
          ? jsxs('div', { style: { display: 'flex', gap: 8, alignItems: 'center', color: c.secondary }, children: [jsx(GlyphSpinner, {}), 'Checking…'] })
          : jsx('div', { children: jsx(Button, { disabled: importer.phase === 'installing', onClick: installImporter, children: importer.phase === 'installing' ? 'Installing…' : 'Install importer' }) }),
        importer.hint && jsx('p', { style: { margin: 0, color: c.tertiary, fontSize: 12 }, children: `Or in a terminal: ${importer.hint}` }),
        importer.error && jsx('p', { style: { margin: 0, color: c.red, fontSize: 13 }, children: importer.error })
      ]
    })
  }

  const fileLine = () => {
    if (scan.phase === 'scanning' && !scan.quiet) {
      return jsxs('span', { style: { display: 'inline-flex', gap: 6, alignItems: 'center', color: c.tertiary, fontSize: 13 }, children: [jsx(GlyphSpinner, {}), 'Looking in Downloads…'] })
    }
    if (files.length) {
      return jsx('p', { style: { margin: 0, color: c.green, fontSize: 13 }, children: `Ready: ${files.length} export${files.length === 1 ? '' : 's'} (${files.map(f => f.split(/[\\/]/).pop()).join(', ')})` })
    }
    if (scan.phase === 'done' && !scan.quiet) {
      return jsx('p', { style: { margin: 0, color: c.tertiary, fontSize: 13 }, children: 'No export in Downloads yet. When the Bot replies, paste its reply below or choose the file it saved.' })
    }
    return opened
      ? jsx('p', { style: { margin: 0, color: c.tertiary, fontSize: 13 }, children: 'Watching Downloads for the export…' })
      : null
  }

  return jsxs('div', {
    style: { display: 'grid', gap: 12, maxWidth: 760 },
    children: [
      jsx('p', { style: { margin: '0 0 4px', color: c.secondary, fontSize: 13, maxWidth: '62ch' }, children: 'Each Grok Bot becomes its own Hermes bot, with its instructions, skills, memories and routines. It runs on your Hermes model. Routines arrive paused so nothing runs twice, and your Grok Bots stay exactly as they are.' }),
      jsx(Step, {
        n: 1,
        title: 'Copy the prompt and open Grok Bot',
        done: opened,
        children: jsxs('div', {
          style: { display: 'grid', gap: 8 },
          children: [
            jsx('p', { style: { margin: 0, color: c.tertiary, fontSize: 13 }, children: 'Paste it into a Bot\'s chat and send. The Bot replies with its export and saves it to Downloads when it can. Repeat for every Bot you want to bring.' }),
            jsxs('div', {
              style: { display: 'flex', gap: 8, flexWrap: 'wrap' },
              children: [
                jsx(Button, { disabled: !prompt, onClick: openGrok, children: 'Copy prompt and open Grok Bot' }),
                jsx(Button, { variant: 'ghost', disabled: !prompt, onClick: copy, children: copied ? 'Copied' : 'Copy prompt only' })
              ]
            }),
            jsxs('details', { children: [
              jsx('summary', { style: { cursor: 'pointer', color: c.tertiary, fontSize: 12 }, children: 'Read the prompt' }),
              jsx('pre', { style: { margin: '8px 0 0', maxHeight: 160, overflow: 'auto', whiteSpace: 'pre-wrap', fontSize: 11.5, color: c.tertiary, fontFamily: 'var(--font-mono, ui-monospace)', border: `1px solid ${c.stroke}`, borderRadius: 8, padding: 10 }, children: prompt })
            ] })
          ]
        })
      }),
      jsx(Step, {
        n: 2,
        title: 'Bring the export back',
        done: st.phase === 'done',
        children: jsxs('div', {
          style: { display: 'grid', gap: 8 },
          children: [
            fileLine(),
            jsx(Textarea, { rows: 4, value: text, placeholder: 'Or paste the Bot\'s whole reply here (paste several replies one after another)', onChange: e => setText(e.target.value) }),
            jsxs('div', {
              style: { display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' },
              children: [
                jsx(Button, { disabled: !haveInput || st.phase === 'reading' || st.phase === 'migrating', onClick: check, children: st.phase === 'reading' ? 'Reading…' : haveText ? 'Review pasted reply' : files.length ? `Review ${files.length === 1 ? 'export' : `${files.length} exports`}` : 'Review bots' }),
                jsx(Button, { variant: 'ghost', disabled: scan.phase === 'scanning', onClick: () => void scanDownloads(false), children: scan.phase === 'scanning' ? 'Looking…' : 'Check Downloads' }),
                jsx(Button, { variant: 'ghost', onClick: chooseFile, children: 'Choose file…' })
              ]
            })
          ]
        })
      }),
      st.phase === 'error' && jsx('p', { role: 'alert', style: { color: c.red, margin: 0, fontSize: 13 }, children: st.error }),
      pv &&
        jsxs('div', {
          style: { ...box, display: 'grid', gap: 14 },
          children: [
            ...pv.bots.map(b =>
              jsxs('div', {
                style: { display: 'grid', gap: 8, paddingBottom: 12, borderBottom: `1px solid ${c.stroke}`, opacity: skip[b.name] ? 0.5 : 1 },
                children: [
                  jsxs('div', {
                    style: { display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' },
                    children: [
                      jsx('input', { type: 'checkbox', checked: !skip[b.name], disabled: st.phase !== 'preview', onChange: e => setSkip(s => ({ ...s, [b.name]: !e.target.checked })), 'aria-label': `Move ${b.name}` }),
                      jsx('strong', { style: { color: c.primary, fontSize: 15 }, children: b.name }),
                      b.title && jsx('span', { style: { color: c.tertiary, fontSize: 13 }, children: b.title }),
                      jsx('span', { style: { flex: 1 } }),
                      b.existing
                        ? jsx('span', { style: { color: c.tertiary, fontSize: 12 }, children: `adds new items to “${b.profile}”` })
                        : jsx(Input, { value: names[b.name] || '', disabled: st.phase !== 'preview', onChange: e => setNames(n => ({ ...n, [b.name]: e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, '-') })), style: { width: 180 }, 'aria-label': `Hermes name for ${b.name}` })
                    ]
                  }),
                  jsxs('div', {
                    style: { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 12 },
                    children: [
                      jsx(Section, { title: 'Skills', children: jsx(List, { items: b.skills, empty: 'None' }) }),
                      jsx(Section, { title: 'Routines (paused)', children: jsx(List, { items: b.routines, empty: 'None' }) }),
                      jsx(Section, { title: 'Memory', children: jsx(List, { items: [`${b.memories} memories`, `${b.user_facts} facts about you`], empty: '' }) }),
                      (b.apps.length > 0 || b.event_routines.length > 0) &&
                        jsx(Section, { title: 'To reconnect', children: jsx(List, { items: [...b.apps.map(a => `${a} (app)`), ...b.event_routines.map(r => `${r} (event routine, saved as notes)`)], empty: '' }) })
                    ]
                  })
                ]
              }, b.name)
            ),
            st.phase !== 'done' &&
              jsxs('div', {
                style: { display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' },
                children: [
                  jsx(Button, { disabled: st.phase === 'migrating' || pv.bots.every(b => skip[b.name]), onClick: run, children: st.phase === 'migrating' ? 'Moving…' : `Move ${pv.bots.filter(b => !skip[b.name]).length === 1 ? 'it' : 'them'} to Hermes` }),
                  jsx('span', { style: { color: c.tertiary, fontSize: 12 }, children: 'Never moves keys, passwords or app logins.' })
                ]
              }),
            st.error && st.phase !== 'error' && jsx('p', { role: 'alert', style: { color: c.red, margin: 0, fontSize: 13 }, children: st.error }),
            st.phase === 'done' &&
              jsxs('div', {
                style: { display: 'grid', gap: 10 },
                children: st.out.results.map(r =>
                  jsxs('div', {
                    style: { display: 'grid', gap: 6 },
                    children: [
                      jsxs('p', {
                        style: { margin: 0, color: c.secondary, fontSize: 13 },
                        children: [
                          jsx('span', { style: { color: c.green }, children: `${r.bot} is now “${r.profile}”. ` }),
                          r.routines_paused > 0 ? `${r.routines_paused} routine(s) paused: turn the Grok copy off, then resume it from this bot's Cron tab. ` : '',
                          r.notes.length ? r.notes.join(' ') : ''
                        ]
                      }),
                      jsx('div', { children: jsx(Button, { variant: 'secondary', onClick: () => host.newChat(r.profile), children: `Chat with ${r.bot}` }) })
                    ]
                  }, r.profile)
                )
              })
          ]
        })
    ]
  })
}

// ------------------------------------------------------------------ page --
function Page() {
  const [tab, setTab] = useState('add')
  const [addRef, setAddRef] = useState('')
  const [wrong, setWrong] = useState(null)
  const [epoch, setEpoch] = useState(0)

  useEffect(() => {
    onWrongProfile = profile => setWrong(profile || 'a bot')
    const unsub = host.state.profile.subscribe?.(pr => {
      if (pr === MAIN_PROFILE) {
        setWrong(w => {
          if (w) {
            setEpoch(x => x + 1)
          }
          return null
        })
      }
    })
    return () => {
      onWrongProfile = null
      unsub?.()
    }
  }, [])

  // A deep link can arrive while this page is already open (the router changes the hash with
  // pushState, which fires no hashchange), so re-read the query on every navigation signal and on
  // a short poll while mounted. The latest link always wins.
  useEffect(() => {
    let last = ''
    const sync = () => {
      const h = window.location.hash || ''
      if (h === last) {
        return
      }
      last = h
      const q = readQuery()
      const add = q.get('add')
      const t = q.get('tab')

      if (add) {
        setTab('add')
        setAddRef(add)
      } else if (t === 'share' || t === 'grok' || t === 'add') {
        setTab(t)
      }
    }

    sync()
    window.addEventListener('hashchange', sync)
    window.addEventListener('popstate', sync)
    const timer = setInterval(sync, 400)

    return () => {
      window.removeEventListener('hashchange', sync)
      window.removeEventListener('popstate', sync)
      clearInterval(timer)
    }
  }, [])

  const tabBtn = (id, text) =>
    jsx('button', {
      type: 'button',
      onClick: () => setTab(id),
      style: {
        background: 'none',
        border: 0,
        padding: '6px 2px',
        marginRight: 18,
        cursor: 'pointer',
        fontSize: 14,
        color: tab === id ? c.primary : c.tertiary,
        borderBottom: `2px solid ${tab === id ? c.accent : 'transparent'}`
      },
      children: text
    })

  return jsxs('div', {
    style: { padding: '28px 32px', overflow: 'auto', height: '100%', boxSizing: 'border-box' },
    children: [
      jsx('h1', { style: { margin: '0 0 4px', fontSize: 24, color: c.primary }, children: 'Community bots' }),
      jsx('p', { style: { margin: '0 0 18px', color: c.tertiary, fontSize: 13 }, children: 'Add bots people made on hermesmade.lol, or share one of yours.' }),
      jsxs('div', { style: { borderBottom: `1px solid ${c.stroke}`, marginBottom: 18 }, children: [tabBtn('add', 'Add a bot'), tabBtn('share', 'Share a bot'), tabBtn('grok', 'Move from Grok Bot')] }),
      wrong &&
        jsxs('div', {
          role: 'alert',
          style: { ...box, display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap', marginBottom: 16 },
          children: [
            jsx('span', { style: { color: c.primary, fontSize: 13, flex: '1 1 320px' }, children: `You're on “${wrong}”. Community bots runs on your main Hermes profile, so switch back to add, share or move bots.` }),
            jsx(Button, { onClick: switchToMain, children: 'Switch to main profile' })
          ]
        }),
      tab === 'add' ? jsx(AddPane, { initial: addRef }, `a${epoch}`) : tab === 'grok' ? jsx(GrokPane, {}, `g${epoch}`) : jsx(SharePane, {}, `s${epoch}`)
    ]
  })
}

export default {
  id: 'hermesmade',
  name: 'hermesmade bots',
  register(ctx) {
    CTX = ctx
    ctx.registerMany([
      { id: 'page', area: ROUTES_AREA, data: { path: ROUTE }, render: () => jsx(Page, {}) },
      { id: 'nav', area: SIDEBAR_NAV_AREA, data: { path: ROUTE, label: 'Community bots', codicon: 'hubot' } },
      { id: 'share', area: PALETTE_AREA, data: { id: 'hm-share', label: 'Share this bot to hermesmade.lol', keywords: ['hermesmade', 'share', 'bot'], run: () => host.navigate(`${ROUTE}?tab=share`) } },
      { id: 'grok', area: PALETTE_AREA, data: { id: 'hm-grok', label: 'Migrate bots from Grok Bot', keywords: ['grok', 'grokbot', 'migrate', 'import', 'bot'], run: () => host.navigate(`${ROUTE}?tab=grok`) } },
      { id: 'add', area: PALETTE_AREA, data: { id: 'hm-add', label: 'Add a community bot', keywords: ['hermesmade', 'add', 'bot'], run: () => host.navigate(ROUTE) } }
    ])
  }
}
