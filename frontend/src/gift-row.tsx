import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Pressable, Share, StyleSheet, Text, TextInput, View } from "react-native";
import FeatherIcon from "@react-native-vector-icons/feather";

import { api, Gift } from "./api";
import { LEVEL_INFO } from "./levels";
import { colors, radius, spacing } from "./theme";

/** One bought gift: code, delivery status, share, and resend / change the friend's email. */
export function GiftRow({ gift: g }: { gift: Gift }) {
  const qc = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [email, setEmail] = useState(g.recipient_email ?? "");
  const send = useMutation({
    mutationFn: () => api.emailGift(g.id, email.trim() || undefined),
    onSettled: () => qc.invalidateQueries({ queryKey: ["my-gifts"] }),
    onSuccess: () => setEditing(false),
  });
  const errMsg = send.error
    ? /check your inputs|valid email/i.test(send.error.message) ? "Enter a valid email address" : send.error.message
    : "";
  const label = LEVEL_INFO[g.level as "silver"].label;
  const status = g.redeemed
    ? `Redeemed by ${g.redeemed_by_name ?? "a friend"}`
    : g.recipient_email
      ? `${g.recipient_email}${g.email_status === "sent" ? " · emailed ✓" : g.email_status ? " · email failed" : ""}`
      : "Not sent yet";

  function share() {
    Share.share({ message: `I got you a month of Nocturne ${label} 🥂 Redeem code ${g.code} in the app under Profile → Gifts.` }).catch(() => {});
  }

  return (
    <View style={styles.card} testID={`gift-${g.code}`}>
      <View style={styles.row}>
        <View style={{ flex: 1 }}>
          <Text style={styles.code}>{g.code}</Text>
          <Text style={styles.muted}>{label} · {status}</Text>
        </View>
        {!g.redeemed ? (
          <>
            <Pressable testID={`gift-email-${g.code}`} onPress={() => setEditing((v) => !v)} style={styles.iconBtn}>
              <FeatherIcon name="mail" size={16} color={colors.brandPrimary} />
            </Pressable>
            <Pressable testID={`gift-share-${g.code}`} onPress={share} style={styles.iconBtn}>
              <FeatherIcon name="share-2" size={16} color={colors.brandPrimary} />
            </Pressable>
          </>
        ) : null}
      </View>
      {editing ? (
        <View style={styles.row}>
          <TextInput
            testID={`gift-email-input-${g.code}`}
            value={email}
            onChangeText={setEmail}
            placeholder="Friend's email"
            placeholderTextColor={colors.muted}
            keyboardType="email-address"
            autoCapitalize="none"
            style={styles.input}
          />
          <Pressable
            testID={`gift-send-${g.code}`}
            disabled={!email.trim() || send.isPending}
            onPress={() => send.mutate()}
            style={[styles.sendBtn, (!email.trim() || send.isPending) && { opacity: 0.5 }]}
          >
            <Text style={styles.sendText}>{send.isPending ? "…" : g.email_status === "sent" && email.trim() === g.recipient_email ? "Resend" : "Send"}</Text>
          </Pressable>
        </View>
      ) : null}
      {errMsg ? <Text style={styles.err} testID={`gift-send-error-${g.code}`}>{errMsg}</Text> : null}
      {send.isSuccess && !editing ? <Text style={styles.ok}>Sent to {send.data.recipient_email}</Text> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  card: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, padding: spacing.md, borderWidth: 1, borderColor: colors.border, gap: spacing.sm },
  row: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  code: { color: colors.brandPrimary, fontSize: 16, fontWeight: "900", letterSpacing: 1 },
  muted: { color: colors.muted, fontSize: 13 },
  iconBtn: { width: 44, height: 44, borderRadius: 22, borderWidth: 1, borderColor: colors.brandPrimary, alignItems: "center", justifyContent: "center" },
  input: {
    flex: 1, minHeight: 44, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface,
    color: colors.onSurface, paddingHorizontal: spacing.md, fontSize: 15,
  },
  sendBtn: { minHeight: 44, paddingHorizontal: spacing.lg, borderRadius: radius.md, backgroundColor: colors.brandPrimary, justifyContent: "center" },
  sendText: { color: colors.onBrandPrimary, fontSize: 14, fontWeight: "800" },
  err: { color: colors.error, fontSize: 13 },
  ok: { color: colors.success, fontSize: 13 },
});
