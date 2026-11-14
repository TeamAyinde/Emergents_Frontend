import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Image } from "expo-image";
import { useRouter } from "expo-router";
import { useEffect, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Switch, Text, TextInput, View } from "react-native";
import { KeyboardAwareScrollView } from "react-native-keyboard-controller";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import FeatherIcon from "@react-native-vector-icons/feather";

import { api } from "@/src/api";
import { Level, LEVEL_INFO } from "@/src/levels";
import { colors, radius, spacing } from "@/src/theme";
import { LuxButton } from "@/src/ui";

const U = "https://images.unsplash.com/";
const COVERS = [
  U + "photo-1545128485-c400e7702796?w=1400&q=80",
  U + "photo-1630395822970-acd6a691d97e?w=1400&q=80",
  U + "photo-1574391884720-bbc3740c59d1?w=1400&q=80",
  U + "photo-1514933651103-005eec06c04b?w=1400&q=80",
];
const TIMES = [19, 20, 21, 22, 23];
const TAGS = ["DJ", "VIP", "Open Bar", "Live Music", "Dress Code", "Latin", "Hip-Hop", "House"];

export default function NewEvent() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const qc = useQueryClient();
  const { data: venues, refetch: refetchVenues } = useQuery({ queryKey: ["host-venues"], queryFn: () => api.hostVenues() });
  const [venueId, setVenueId] = useState("");
  const [newVenue, setNewVenue] = useState({ name: "", city: "", category: "Lounge" });
  const [title, setTitle] = useState("");
  const [desc, setDesc] = useState("");
  const [price, setPrice] = useState("40");
  const [day, setDay] = useState(0);
  const [hour, setHour] = useState(22);
  const [cover, setCover] = useState(COVERS[0]);
  const [tags, setTags] = useState<string[]>(["DJ"]);
  const [level, setLevel] = useState<Level>("bronze");
  const [capacity, setCapacity] = useState("150");
  const [plusOnes, setPlusOnes] = useState(3);
  const [approval, setApproval] = useState(false);
  const [showGuests, setShowGuests] = useState(true);
  const [tables, setTables] = useState(true);
  const [tableMin, setTableMin] = useState("500");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => {
    if (!venueId && venues?.length) setVenueId(venues[0].id);
  }, [venues, venueId]);

  const days = Array.from({ length: 30 }, (_, i) => {
    const d = new Date();
    d.setDate(d.getDate() + i + 1);
    return d;
  });

  async function submit() {
    setErr("");
    if (!title.trim()) return setErr("Give your event a title");
    const p = parseFloat(price);
    if (isNaN(p) || p < 0) return setErr("Enter a valid ticket price");
    setBusy(true);
    try {
      let vid = venueId;
      if (!vid) {
        if (!newVenue.name.trim() || !newVenue.city.trim()) throw new Error("Add your venue name and city");
        const v = await api.createVenue({ ...newVenue, image_url: cover, description: "" });
        vid = v.id;
        await refetchVenues();
      }
      const date = new Date(days[day]);
      date.setHours(hour, 0, 0, 0);
      const ev = await api.createEvent({
        title: title.trim(), venue_id: vid, date: date.toISOString(), price: p, image_url: cover,
        description: desc.trim() || "An unforgettable night. Dress to impress.", tags, min_level: level,
        capacity: Math.max(1, parseInt(capacity, 10) || 150), approval_required: approval, plus_one_limit: plusOnes,
        guest_list_visible: showGuests, table_min_spend: tables ? Math.max(0, parseFloat(tableMin) || 0) || null : null,
      });
      qc.invalidateQueries({ queryKey: ["host-events"] });
      qc.invalidateQueries({ queryKey: ["events"] });
      router.replace(`/event/${ev.id}`);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not create event");
    } finally {
      setBusy(false);
    }
  }

  return (
    <View style={styles.root}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.md }]}>
        <Pressable testID="new-event-back" onPress={() => router.back()} style={styles.iconBtn}>
          <FeatherIcon name="x" size={20} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.title}>New event</Text>
        <View style={{ width: 44 }} />
      </View>
      <KeyboardAwareScrollView
        bottomOffset={24}
        keyboardShouldPersistTaps="handled"
        contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + spacing["2xl"], gap: spacing.md }}
      >
        <Label t="Venue" />
        {venues && venues.length > 0 ? (
          <Chips items={venues.map((v) => ({ key: v.id, label: v.name }))} value={venueId} onChange={setVenueId} prefix="venue" />
        ) : (
          <View style={{ gap: spacing.sm }}>
            <Input testID="new-venue-name" value={newVenue.name} onChangeText={(v) => setNewVenue({ ...newVenue, name: v })} placeholder="Venue name" />
            <Input testID="new-venue-city" value={newVenue.city} onChangeText={(v) => setNewVenue({ ...newVenue, city: v })} placeholder="City" />
            <Chips items={["Lounge", "Nightclub", "Restaurant & Bar", "Rooftop", "Private Venue"].map((c) => ({ key: c, label: c }))}
              value={newVenue.category} onChange={(c) => setNewVenue({ ...newVenue, category: c })} prefix="venue-cat" />
          </View>
        )}

        <Label t="Title" />
        <Input testID="new-event-title" value={title} onChangeText={setTitle} placeholder="Midnight Gold — Grand Opening" />
        <Label t="Description" />
        <Input testID="new-event-desc" value={desc} onChangeText={setDesc} placeholder="Lineup, dress code, what to expect" multiline />

        <Label t="Cover" />
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: spacing.sm }}>
          {COVERS.map((c, i) => (
            <Pressable key={c} testID={`cover-${i}`} onPress={() => setCover(c)} style={[styles.cover, cover === c && styles.coverOn]}>
              <Image source={c} style={StyleSheet.absoluteFill} contentFit="cover" />
            </Pressable>
          ))}
        </ScrollView>

        <Label t="Date" />
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: spacing.sm }}>
          {days.map((d, i) => (
            <Pressable key={i} testID={`new-event-day-${i}`} onPress={() => setDay(i)} style={[styles.day, day === i && styles.on]}>
              <Text style={styles.dow}>{d.toLocaleDateString("en", { weekday: "short" }).toUpperCase()}</Text>
              <Text style={[styles.dnum, day === i && { color: colors.brandPrimary }]}>{d.getDate()}</Text>
            </Pressable>
          ))}
        </ScrollView>
        <Chips items={TIMES.map((h) => ({ key: String(h), label: `${h > 12 ? h - 12 : h} PM` }))} value={String(hour)} onChange={(v) => setHour(Number(v))} prefix="time" />

        <Label t="Ticket price ($)" />
        <Input testID="new-event-price" value={price} onChangeText={setPrice} keyboardType="decimal-pad" />
        <Label t="Capacity" />
        <Input testID="new-event-capacity" value={capacity} onChangeText={setCapacity} keyboardType="number-pad" />

        <Label t="Who can attend" />
        <Chips items={(["bronze", "silver", "gold"] as Level[]).map((l) => ({ key: l, label: `${LEVEL_INFO[l].label}+` }))} value={level} onChange={(v) => setLevel(v as Level)} prefix="level" />

        <Label t="Plus-ones per guest" />
        <Chips items={[0, 1, 2, 3].map((n) => ({ key: String(n), label: n === 0 ? "None" : `+${n}` }))} value={String(plusOnes)} onChange={(v) => setPlusOnes(Number(v))} prefix="plus" />

        <Label t="Tags" />
        <View style={styles.wrap}>
          {TAGS.map((t) => {
            const on = tags.includes(t);
            return (
              <Pressable key={t} testID={`tag-${t}`} onPress={() => setTags(on ? tags.filter((x) => x !== t) : [...tags, t])} style={[styles.chip, on && styles.chipOn]}>
                <Text style={[styles.chipText, on && styles.chipTextOn]}>{t}</Text>
              </Pressable>
            );
          })}
        </View>

        <Toggle testID="toggle-approval" label="Guests need my approval" value={approval} onChange={setApproval} />
        <Toggle testID="toggle-guestlist" label="Show who's going" value={showGuests} onChange={setShowGuests} />
        <Toggle testID="toggle-tables" label="Sell tables & VIP packages" value={tables} onChange={setTables} />
        {tables ? (
          <>
            <Label t="Main-floor table minimum ($) — VIP 2×, Skybox 4×" />
            <Input testID="new-event-table-min" value={tableMin} onChangeText={setTableMin} keyboardType="number-pad" />
          </>
        ) : null}

        {err ? <Text style={styles.err} testID="new-event-error">{err}</Text> : null}
        <LuxButton testID="new-event-submit" label={busy ? "Publishing…" : "Publish event"} onPress={submit} loading={busy} />
      </KeyboardAwareScrollView>
    </View>
  );
}

function Label({ t }: { t: string }) {
  return <Text style={styles.label}>{t}</Text>;
}
function Input(props: React.ComponentProps<typeof TextInput>) {
  return <TextInput placeholderTextColor={colors.muted} {...props} style={[styles.input, props.multiline && { minHeight: 88, textAlignVertical: "top" }]} />;
}
function Chips({ items, value, onChange, prefix }: { items: { key: string; label: string }[]; value: string; onChange: (k: string) => void; prefix: string }) {
  return (
    <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: spacing.sm }}>
      {items.map((i) => (
        <Pressable key={i.key} testID={`${prefix}-${i.key}`} onPress={() => onChange(i.key)} style={[styles.chip, value === i.key && styles.chipOn]}>
          <Text style={[styles.chipText, value === i.key && styles.chipTextOn]}>{i.label}</Text>
        </Pressable>
      ))}
    </ScrollView>
  );
}
function Toggle({ label, value, onChange, testID }: { label: string; value: boolean; onChange: (v: boolean) => void; testID: string }) {
  return (
    <View style={styles.toggle}>
      <Text style={styles.toggleText}>{label}</Text>
      <Switch testID={testID} value={value} onValueChange={onChange} thumbColor={colors.onSurface} trackColor={{ true: colors.brandPrimary, false: colors.surfaceTertiary }} />
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.lg, paddingBottom: spacing.sm },
  iconBtn: {
    width: 44, height: 44, borderRadius: 22, backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border,
    alignItems: "center", justifyContent: "center",
  },
  title: { color: colors.onSurface, fontSize: 17, fontWeight: "700" },
  label: { color: colors.muted, fontSize: 12, letterSpacing: 1, textTransform: "uppercase", marginTop: spacing.xs },
  input: {
    backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md,
    paddingHorizontal: spacing.lg, paddingVertical: 14, color: colors.onSurface, fontSize: 15,
  },
  cover: { width: 120, height: 80, borderRadius: radius.md, overflow: "hidden", borderWidth: 2, borderColor: "transparent" },
  coverOn: { borderColor: colors.brandPrimary },
  day: { flexShrink: 0, width: 56, height: 64, borderRadius: radius.md, borderWidth: 1.5, borderColor: colors.border, backgroundColor: colors.surfaceSecondary, alignItems: "center", justifyContent: "center" },
  on: { borderColor: colors.brandPrimary, backgroundColor: colors.brandTertiary },
  dow: { color: colors.muted, fontSize: 10, fontWeight: "700", letterSpacing: 1 },
  dnum: { color: colors.onSurface, fontSize: 20, fontWeight: "800" },
  wrap: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  chip: { flexShrink: 0, height: 40, paddingHorizontal: spacing.lg, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary, alignItems: "center", justifyContent: "center" },
  chipOn: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  chipText: { color: colors.onSurfaceSecondary, fontSize: 13, fontWeight: "600" },
  chipTextOn: { color: colors.onBrandPrimary },
  toggle: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", minHeight: 48 },
  toggleText: { color: colors.onSurface, fontSize: 15 },
  err: { color: colors.error, fontSize: 13 },
});
