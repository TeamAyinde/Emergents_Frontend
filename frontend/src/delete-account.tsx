import { useState } from "react";
import { ActivityIndicator, Alert, Platform, Pressable, StyleSheet, Text, View } from "react-native";
import FeatherIcon from "@react-native-vector-icons/feather";

import { api } from "./api";
import { useAuth } from "./auth-context";
import { colors, radius, spacing } from "./theme";

const WARNING =
  "This permanently deletes your Nocturne account, membership, concierge messages, reports and points. " +
  "Any active membership is cancelled. Tickets you've bought stop working. This can't be undone.";

/** Profile: permanent account deletion with a clear confirmation step. */
export function DeleteAccountRow() {
  const { signOut } = useAuth();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const run = async () => {
    setBusy(true);
    setErr("");
    try {
      await api.deleteMyAccount();
      await signOut();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Couldn't delete your account");
    } finally {
      setBusy(false);
    }
  };

  const confirm = () => {
    if (Platform.OS === "web") {
      const typed = window.prompt(`${WARNING}\n\nType DELETE to confirm.`);
      if (typed?.trim().toUpperCase() === "DELETE") run();
      return;
    }
    Alert.alert("Delete your account?", WARNING, [
      { text: "Cancel", style: "cancel" },
      { text: "Delete forever", style: "destructive", onPress: run },
    ]);
  };

  return (
    <View>
      <Pressable testID="delete-account-btn" onPress={confirm} disabled={busy} style={styles.row} accessibilityRole="button">
        {busy ? <ActivityIndicator color={colors.error} /> : <FeatherIcon name="trash-2" size={16} color={colors.error} />}
        <Text style={styles.text}>Delete account</Text>
      </Pressable>
      {err ? <Text style={styles.err} testID="delete-account-error">{err}</Text> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm, minHeight: 48,
    borderRadius: radius.pill, borderWidth: 1, borderColor: colors.error,
  },
  text: { color: colors.error, fontWeight: "700", fontSize: 15 },
  err: { color: colors.error, fontSize: 13, textAlign: "center", marginTop: spacing.sm },
});
