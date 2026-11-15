import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Platform, StyleSheet, Switch, Text, View } from "react-native";

import { api } from "./api";
import { colors, radius, spacing } from "./theme";

/** Host event screen: pick who works the door this night. */
export function ShiftsCard({ eventId }: { eventId: string }) {
  const qc = useQueryClient();
  const { data } = useQuery({ queryKey: ["shifts", eventId], queryFn: () => api.eventShifts(eventId) });
  const toggle = useMutation({
    mutationFn: ({ sid, on }: { sid: string; on: boolean }) => api.setShift(eventId, sid, on),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["shifts", eventId] });
      qc.invalidateQueries({ queryKey: ["door-staff"] });
    },
  });
  const change = (sid: string, on: boolean, everyNight: boolean, name: string) => {
    if (on || !everyNight) return toggle.mutate({ sid, on });
    const msg = `${name} works every night right now. Taking them off this night switches them to shifts only, so they'll only see nights you turn on.`;
    if (Platform.OS === "web") {
      if (window.confirm(`Switch to shifts only?\n${msg}`)) toggle.mutate({ sid, on });
      return;
    }
    Alert.alert("Switch to shifts only?", msg, [
      { text: "Cancel", style: "cancel" },
      { text: "Switch", onPress: () => toggle.mutate({ sid, on }) },
    ]);
  };
  if (!data || data.length === 0) return null;

  return (
    <View style={styles.card} testID="shifts-card">
      <Text style={styles.title}>Door team tonight</Text>
      <Text style={styles.sub}>Staff only see and scan the nights they're on.</Text>
      {data.map((s) => (
        <View key={s.staff_id} style={styles.row} testID={`shift-row-${s.staff_id}`}>
          <View style={{ flex: 1 }}>
            <Text style={styles.name} numberOfLines={1}>{s.status === "invited" ? s.email : s.name}</Text>
            <Text style={styles.sub}>{s.every_night ? "Every night" : s.on_shift ? "On shift" : "Off"}</Text>
          </View>
          <Switch
            testID={`shift-${s.staff_id}`}
            value={s.on_shift}
            disabled={toggle.isPending}
            onValueChange={(on) => change(s.staff_id, on, s.every_night, s.status === "invited" ? s.email : s.name)}
            trackColor={{ true: colors.brandPrimary, false: colors.borderStrong }}
            thumbColor={colors.onSurface}
          />
        </View>
      ))}
      {toggle.error ? <Text style={styles.err}>{toggle.error.message}</Text> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  card: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, padding: spacing.lg, gap: spacing.sm, borderWidth: 1, borderColor: colors.border },
  title: { color: colors.onSurface, fontSize: 17, fontWeight: "800" },
  sub: { color: colors.muted, fontSize: 13 },
  row: { flexDirection: "row", alignItems: "center", gap: spacing.md, minHeight: 52, borderTopWidth: 0.5, borderTopColor: colors.divider },
  name: { color: colors.onSurface, fontSize: 15, fontWeight: "700" },
  err: { color: colors.error, fontSize: 13 },
});
