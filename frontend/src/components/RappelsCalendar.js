import React, { useMemo, useState } from "react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ChevronLeft, ChevronRight, List } from "lucide-react";
import {
  RAPPEL_CALENDAR_CHIP,
  WEEKDAY_LABELS_FR,
  addDays,
  addMonths,
  buildMonthGrid,
  buildWeekDays,
  filterRappelsForCalendar,
  formatPeriodTitle,
  groupRappelsByIsoDate,
  isSameDay,
  rappelCalendarLabel,
  rappelStatutEffectif,
  toIsoDate,
  uniqueRappelAuthors,
} from "@/lib/rappels";

const STATUS_FILTERS = [
  { id: "all", label: "Tous" },
  { id: "a_faire", label: "À faire" },
  { id: "en_attente", label: "En attente" },
  { id: "termine", label: "Terminés" },
];

const MODE_OPTIONS = [
  { id: "month", label: "Mois" },
  { id: "week", label: "Semaine" },
  { id: "day", label: "Jour" },
];

function Chip({ rappel, now, onClick, compact }) {
  const effectif = rappelStatutEffectif(rappel, now);
  const style = RAPPEL_CALENDAR_CHIP[effectif] || RAPPEL_CALENDAR_CHIP.a_faire;
  const label = rappelCalendarLabel(rappel);
  return (
    <button
      type="button"
      data-testid={`rappel-cal-chip-${rappel.id}`}
      title={label}
      onClick={(e) => {
        e.stopPropagation();
        onClick?.(rappel);
      }}
      className={`w-full text-left rounded border px-1.5 py-0.5 text-[10px] sm:text-[11px] leading-snug font-medium truncate transition-colors ${style} ${
        compact ? "mb-0.5" : "mb-1"
      }`}
    >
      {label}
    </button>
  );
}

function DayCell({
  day,
  items,
  now,
  today,
  tall,
  canCreate,
  onDayClick,
  onRappelClick,
}) {
  const isToday = isSameDay(day.date, today);
  const maxShow = tall ? 8 : 3;
  const visible = items.slice(0, maxShow);
  const more = items.length - visible.length;

  return (
    <div
      role="button"
      tabIndex={0}
      data-testid={`rappel-cal-day-${day.iso}`}
      onClick={() => onDayClick?.(day.iso, items)}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onDayClick?.(day.iso, items);
        }
      }}
      className={`min-h-[5.5rem] sm:min-h-[6.5rem] ${tall ? "min-h-[10rem] sm:min-h-[12rem]" : ""} border border-border/70 p-1.5 text-left transition-colors hover:bg-[#002FA7]/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#002FA7]/30 ${
        day.inMonth ? "bg-white" : "bg-slate-50/80 text-muted-foreground"
      } ${isToday ? "ring-1 ring-inset ring-[#002FA7]/40 bg-[#002FA7]/5" : ""} ${
        canCreate ? "cursor-pointer" : ""
      }`}
    >
      <div className="flex items-center justify-between mb-1">
        <span
          className={`inline-flex h-6 w-6 items-center justify-center rounded-full text-xs font-semibold ${
            isToday ? "bg-[#002FA7] text-white" : "text-foreground"
          }`}
        >
          {day.date.getDate()}
        </span>
        {items.length > 0 && (
          <span className="text-[10px] text-muted-foreground">{items.length}</span>
        )}
      </div>
      <div className="space-y-0.5">
        {visible.map((r) => (
          <Chip key={r.id} rappel={r} now={now} onClick={onRappelClick} compact={!tall} />
        ))}
        {more > 0 && (
          <p className="text-[10px] text-muted-foreground px-0.5">+{more} autre{more > 1 ? "s" : ""}</p>
        )}
      </div>
    </div>
  );
}

/**
 * Calendrier visuel des rappels — mêmes données / actions que la liste.
 */
export default function RappelsCalendar({
  rappels = [],
  now = new Date(),
  canEdit = false,
  onSelectRappel,
  onCreateForDate,
}) {
  const [cursor, setCursor] = useState(() => new Date());
  const [mode, setMode] = useState("month");
  const [statusFilter, setStatusFilter] = useState("all");
  const [authorFilter, setAuthorFilter] = useState("all");

  const today = useMemo(() => new Date(), []);
  const authors = useMemo(() => uniqueRappelAuthors(rappels), [rappels]);

  const filtered = useMemo(
    () => filterRappelsForCalendar(rappels, { statusFilter, authorFilter, now }),
    [rappels, statusFilter, authorFilter, now],
  );

  const byDate = useMemo(() => groupRappelsByIsoDate(filtered), [filtered]);

  const periodTitle = formatPeriodTitle(cursor, mode);

  const goPrev = () => {
    if (mode === "month") setCursor((c) => addMonths(c, -1));
    else if (mode === "week") setCursor((c) => addDays(c, -7));
    else setCursor((c) => addDays(c, -1));
  };

  const goNext = () => {
    if (mode === "month") setCursor((c) => addMonths(c, 1));
    else if (mode === "week") setCursor((c) => addDays(c, 7));
    else setCursor((c) => addDays(c, 1));
  };

  const goToday = () => setCursor(new Date());

  const handleDayClick = (iso, items) => {
    if (items?.length > 0) return;
    if (canEdit) onCreateForDate?.(iso);
  };

  const monthDays = useMemo(() => (mode === "month" ? buildMonthGrid(cursor) : []), [mode, cursor]);
  const weekDays = useMemo(() => (mode === "week" ? buildWeekDays(cursor) : []), [mode, cursor]);
  const dayIso = toIsoDate(cursor);
  const dayItems = byDate.get(dayIso) || [];

  return (
    <div className="space-y-4" data-testid="rappels-calendar">
      <div className="flex flex-wrap items-center gap-2 justify-between">
        <div className="flex items-center gap-1.5">
          <Button type="button" size="sm" variant="outline" onClick={goPrev} aria-label="Période précédente">
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <Button type="button" size="sm" variant="outline" onClick={goNext} aria-label="Période suivante">
            <ChevronRight className="h-4 w-4" />
          </Button>
          <Button type="button" size="sm" variant="outline" onClick={goToday}>
            Aujourd&apos;hui
          </Button>
          <h2 className="font-display font-bold text-lg tracking-tight ml-1 min-w-[10rem]">
            {periodTitle}
          </h2>
        </div>
        <div className="flex gap-1 rounded-lg border border-border p-0.5 bg-secondary/40">
          {MODE_OPTIONS.map((m) => (
            <button
              key={m.id}
              type="button"
              onClick={() => setMode(m.id)}
              className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
                mode === m.id ? "bg-[#002FA7] text-white shadow-sm" : "text-muted-foreground hover:text-foreground"
              }`}
            >
              {m.label}
            </button>
          ))}
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {STATUS_FILTERS.map((f) => (
          <Button
            key={f.id}
            size="sm"
            variant={statusFilter === f.id ? "default" : "outline"}
            className={statusFilter === f.id ? "bg-[#002FA7] hover:bg-[#00248a]" : ""}
            onClick={() => setStatusFilter(f.id)}
          >
            {f.label}
          </Button>
        ))}
        {authors.length > 0 && (
          <Select value={authorFilter} onValueChange={setAuthorFilter}>
            <SelectTrigger className="h-8 w-[180px] text-xs ml-auto">
              <SelectValue placeholder="Créateur" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Tous les créateurs</SelectItem>
              {authors.map((a) => (
                <SelectItem key={a} value={a}>
                  {a}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}
      </div>

      <div className="flex flex-wrap gap-3 text-[11px] text-muted-foreground">
        <span className="inline-flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-full bg-red-400" /> Échéance dépassée
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-full bg-amber-400" /> À faire
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-full bg-[#002FA7]" /> En attente
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-full bg-emerald-500" /> Effectué
        </span>
      </div>

      {mode === "month" && (
        <Card className="overflow-hidden p-0 shadow-sm">
          <div className="grid grid-cols-7 border-b border-border bg-secondary/50">
            {WEEKDAY_LABELS_FR.map((label) => (
              <div key={label} className="px-2 py-2 text-center text-[11px] font-semibold text-muted-foreground">
                {label}
              </div>
            ))}
          </div>
          <div className="grid grid-cols-7">
            {monthDays.map((day) => (
              <DayCell
                key={day.iso}
                day={day}
                items={byDate.get(day.iso) || []}
                now={now}
                today={today}
                canCreate={canEdit}
                onDayClick={handleDayClick}
                onRappelClick={onSelectRappel}
              />
            ))}
          </div>
        </Card>
      )}

      {mode === "week" && (
        <Card className="overflow-hidden p-0 shadow-sm">
          <div className="grid grid-cols-7 border-b border-border bg-secondary/50">
            {weekDays.map((day) => (
              <div key={day.iso} className="px-2 py-2 text-center text-[11px] font-semibold text-muted-foreground">
                {WEEKDAY_LABELS_FR[(day.date.getDay() + 6) % 7]}
                <div className={`mt-0.5 text-sm ${isSameDay(day.date, today) ? "text-[#002FA7]" : "text-foreground"}`}>
                  {day.date.getDate()}
                </div>
              </div>
            ))}
          </div>
          <div className="grid grid-cols-7">
            {weekDays.map((day) => (
              <DayCell
                key={day.iso}
                day={day}
                items={byDate.get(day.iso) || []}
                now={now}
                today={today}
                tall
                canCreate={canEdit}
                onDayClick={handleDayClick}
                onRappelClick={onSelectRappel}
              />
            ))}
          </div>
        </Card>
      )}

      {mode === "day" && (
        <Card className="p-4 shadow-sm" data-testid="rappel-cal-day-view">
          <div className="flex items-center justify-between mb-4">
            <p className="text-sm text-muted-foreground">
              {dayItems.length} rappel{dayItems.length !== 1 ? "s" : ""} ce jour
            </p>
            {canEdit && (
              <Button
                size="sm"
                className="bg-[#002FA7] hover:bg-[#00248a]"
                onClick={() => onCreateForDate?.(dayIso)}
              >
                Nouveau sur ce jour
              </Button>
            )}
          </div>
          {dayItems.length === 0 ? (
            <button
              type="button"
              className="w-full rounded-lg border border-dashed border-border py-10 text-sm text-muted-foreground hover:border-[#002FA7]/40 hover:text-[#002FA7] transition-colors"
              onClick={() => canEdit && onCreateForDate?.(dayIso)}
              disabled={!canEdit}
            >
              {canEdit ? "Aucun rappel — cliquer pour en créer un" : "Aucun rappel ce jour"}
            </button>
          ) : (
            <ul className="space-y-2">
              {dayItems.map((r) => {
                const effectif = rappelStatutEffectif(r, now);
                const style = RAPPEL_CALENDAR_CHIP[effectif] || RAPPEL_CALENDAR_CHIP.a_faire;
                return (
                  <li key={r.id}>
                    <button
                      type="button"
                      onClick={() => onSelectRappel?.(r)}
                      className={`w-full text-left rounded-lg border px-3 py-2.5 text-sm transition-colors ${style}`}
                    >
                      <p className="font-semibold">{r.client_name || "Client"}</p>
                      <p className="mt-0.5">{r.heure ? `${String(r.heure).slice(0, 5)} · ` : ""}{r.titre}</p>
                      {r.description ? (
                        <p className="text-xs mt-1 opacity-80 line-clamp-2">{r.description}</p>
                      ) : null}
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </Card>
      )}

      {filtered.length === 0 && (
        <p className="text-sm text-muted-foreground flex items-center gap-2">
          <List className="h-4 w-4" /> Aucun rappel pour ces filtres sur la période affichée.
        </p>
      )}
    </div>
  );
}
