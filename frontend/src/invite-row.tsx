import { useQuery } from "@tanstack/react-query";
import * as Clipboard from "expo-clipboard";
import { useState } from "react";
import { Platform, Pressable, Share, StyleSheet, Text, View } from "react-native";
import FeatherIcon from "@react-native-vector-icons/feather";

import { api } from "./api";
import { colors, radius, spacing } from "./theme";

/** Profile: share your invite code; both friends earn points on the friend's first night. */
export function InviteRow() {
  const { data } = useQuery({ queryKey: ["my-invites"], queryFn: api.myInvites });
  const [copied, setCopied] = useState(false);
  if (!data) return null;

  async function share() {
    const message = `Join me on Nocturne 🥂 Use my invite code ${data!.code} when you sign up and get ${data!.friend_points} bonus points on your first night out.`;
    const canNativeShare = Platform.OS !== "web" || (typeof navigator !== "undefined" && "share" in navigator);
    if (canNativeShare) {
      try {
        await Share.share({ message });
        return;
      } catch {}
    }
    await Clipboard.setStringAsync(message);
    setCopied(true);
    setTimeout(() => setCopied(false), 2500);
  }

  return (
    <Pressable testID="invite-btn" onPress={share} style={styles.row}>
      <View style={styles.icon}>
        <FeatherIcon name="user-plus" size={16} color={colors.brandPrimary} />
      </View>
      <View style={{ flex: 1 }}>
        <Text style={styles.title}>Invite friends · code {data.code}</Text>
        <Text style={styles.sub} testID="invite-stats">
          {copied ? "Invite copied — paste it to a friend" : `${data.referrer_points} points for you, ${data.friend_points} for them on their first night`}
          {!copied && data.invited ? ` · ${data.invited} joined, ${data.points_earned} pts earned` : ""}
        </Text>
      </View>
      <FeatherIcon name="share-2" size={18} color={colors.brandPrimary} />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: "row", alignItems: "center", gap: spacing.md, minHeight: 64, backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md, padding: spacing.md, borderWidth: 1, borderColor: colors.brandPrimary,
  },
  icon: { width: 36, height: 36, borderRadius: 18, backgroundColor: colors.surfaceTertiary, alignItems: "center", justifyContent: "center" },
  title: { color: colors.onSurface, fontSize: 15, fontWeight: "700" },
  sub: { color: colors.muted, fontSize: 12, marginTop: 2 },
});
