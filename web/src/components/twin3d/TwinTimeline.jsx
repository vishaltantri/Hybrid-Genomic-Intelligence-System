import React from 'react'

/** Horizontal timeline built only from stored events (twin.timeline). One event => one marker; nothing is filled in. */
export default function TwinTimeline({ timeline, large = false }) {
  const events = timeline?.events || []
  if (!events.length) {
    return <div className="p-4 text-xs text-on-surface-variant" data-testid="twin-timeline-visual">No dated events are stored for this patient.</div>
  }
  const groups = []
  events.forEach((e) => {
    const day = (e.timestamp_utc || '').slice(0, 10) || 'undated'
    const last = groups[groups.length - 1]
    if (last && last.day === day) last.items.push(e)
    else groups.push({ day, items: [e] })
  })
  return (
    <div className={`w-full ${large ? 'h-full flex flex-col justify-center p-4' : 'p-2'}`} data-testid="twin-timeline-visual">
      <div className="overflow-x-auto">
        <ol className="relative flex items-start gap-8 min-w-max px-4 pt-3 pb-2">
          <div className="absolute left-4 right-4 top-[22px] h-px bg-outline-variant" aria-hidden />
          {groups.map((g) => (
            <li key={g.day} className="relative w-44" data-testid={`timeline-day-${g.day}`}>
              <div className="text-[11px] font-mono font-semibold text-primary">{g.day}</div>
              <span className="block w-2.5 h-2.5 rounded-full bg-primary border-2 border-white shadow my-1.5 relative z-10" />
              <ul className="space-y-1">
                {g.items.map((e, i) => (
                  <li key={`${e.source.ref}-${i}`} className="text-[11px] leading-snug">
                    <span className="font-semibold text-on-surface">{e.title}</span>
                    {large && e.detail && <div className="text-on-surface-variant">{e.detail}</div>}
                    {large && <div className="text-[10px] font-mono text-outline">{e.timestamp_utc?.slice(11, 19)} · {e.source.ref}</div>}
                  </li>
                ))}
              </ul>
            </li>
          ))}
        </ol>
      </div>
      {timeline?.note && <p className="text-[11px] text-amber-800 px-4 mt-1">{timeline.note}</p>}
    </div>
  )
}
