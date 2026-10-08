'use client';

import { MessageCircle, Send, X } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { askAssistant } from '@/lib/assistant';

type Msg = { role: 'bot' | 'user'; text: string };

const CHIPS = ['Scoring limits', 'Free Lab privacy', 'Verify a PAR', 'What is in the demo?'];
const GREETING = 'Product guide. Answers come from curated product information and include their source page.';

export default function Chatbot() {
  const [open, setOpen] = useState(false);
  const [msgs, setMsgs] = useState<Msg[]>([{ role: 'bot', text: GREETING }]);
  const [value, setValue] = useState('');
  const [busy, setBusy] = useState(false);
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => { end.current?.scrollIntoView({ behavior: 'smooth' }); }, [msgs, open]);
  async function send(text: string) {
    const question = text.trim();
    if (!question || busy) return;
    setMsgs(list => [...list, { role: 'user', text: question }]);
    setValue('');
    setBusy(true);
    try {
      const reply = await askAssistant(question);
      setMsgs(list => [...list, { role: 'bot', text: reply.text }]);
    } finally {
      setBusy(false);
    }
  }
  return <>
    <button className="chat-fab" onClick={() => setOpen(!open)} aria-label={open ? 'Close guide chat' : 'Open guide chat'} title="Ask the guide">{open ? <X size={20} /> : <MessageCircle size={20} />}</button>
    {open ? <section className="chat-panel" aria-label="Product guide chat" onKeyDown={event => { if (event.key === 'Escape') setOpen(false); }}>
      <div className="chat-head">Verification guide<span className="mono muted">PUBLIC INFO ONLY</span></div>
      <div className="chat-msgs" role="log" aria-live="polite">
        {msgs.map((msg, index) => <div key={index} className={`chat-msg ${msg.role}`}>{msg.text}</div>)}
        {busy ? <div className="chat-msg bot">Thinking…</div> : null}
        <div ref={end} />
      </div>
      <div className="chat-chips">{CHIPS.map(chip => <button key={chip} onClick={() => send(chip)}>{chip}</button>)}</div>
      <form className="chat-input" onSubmit={event => { event.preventDefault(); send(value); }}>
        <input value={value} onChange={event => setValue(event.target.value)} placeholder="Ask about verification…" aria-label="Ask about verification" maxLength={500} />
        <button className="button primary" type="submit" aria-label="Send message"><Send size={14} /></button>
      </form>
      <div className="chat-note">Curated product guidance. No external AI service receives your question.</div>
    </section> : null}
  </>;
}
