import { useEffect, useRef, useState } from "react";
import { ActivityIndicator, FlatList, Platform, Pressable, StyleSheet, Text, TextInput, View } from "react-native";
import { KeyboardAvoidingView } from "react-native-keyboard-controller";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import FeatherIcon from "@react-native-vector-icons/feather";

import type { ChatMessage } from "./api";
import { colors, radius, spacing } from "./theme";

/** Shared chat UI. `mine` decides which side a message sits on. Polls every 4s. */
export function ChatView({
  load,
  send,
  mine,
  placeholder,
  emptyText,
  suggestions = [],
}: {
  load: () => Promise<ChatMessage[]>;
  send: (text: string) => Promise<unknown>;
  mine: (m: ChatMessage) => boolean;
  placeholder: string;
  emptyText: string;
  suggestions?: string[];
}) {
  const insets = useSafeAreaInsets();
  const [messages, setMessages] = useState<ChatMessage[] | null>(null);
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);
  const [err, setErr] = useState("");
  const loadRef = useRef(load);
  loadRef.current = load;

  useEffect(() => {
    let alive = true;
    const tick = () => loadRef.current().then((m) => alive && setMessages(m)).catch(() => {});
    tick();
    const t = setInterval(tick, 4000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, []);

  async function onSend(value = text) {
    const v = value.trim();
    if (!v || sending) return;
    setSending(true);
    setErr("");
    try {
      await send(v);
      setText("");
      setMessages(await load());
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not send");
    } finally {
      setSending(false);
    }
  }

  const data = [...(messages ?? [])].reverse();
  return (
    <KeyboardAvoidingView behavior="padding" style={{ flex: 1 }} keyboardVerticalOffset={0}>
      {messages === null ? (
        <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: spacing["2xl"] }} />
      ) : (
        <FlatList
          testID="chat-list"
          inverted={data.length > 0}
          data={data}
          keyExtractor={(m) => m.id}
          contentContainerStyle={{ padding: spacing.lg, gap: spacing.sm, flexGrow: 1 }}
          keyboardShouldPersistTaps="handled"
          ListEmptyComponent={
            <View style={styles.empty}>
              <FeatherIcon name="message-circle" size={32} color={colors.brandPrimary} />
              <Text style={styles.emptyText}>{emptyText}</Text>
              {suggestions.map((s) => (
                <Pressable key={s} testID={`chat-suggestion-${s.slice(0, 12)}`} onPress={() => onSend(s)} style={styles.suggestion}>
                  <Text style={styles.suggestionText}>{s}</Text>
                </Pressable>
              ))}
            </View>
          }
          renderItem={({ item }) => {
            const me = mine(item);
            return (
              <View style={[styles.bubbleWrap, me ? styles.right : styles.left]}>
                {!me ? <Text style={styles.sender}>{item.sender_name}</Text> : null}
                <View style={[styles.bubble, me ? styles.bubbleMe : styles.bubbleThem]}>
                  <Text style={[styles.msg, me && { color: colors.onBrandPrimary }]}>{item.text}</Text>
                </View>
                <Text style={styles.time}>
                  {new Date(item.created_at).toLocaleTimeString("en", { hour: "numeric", minute: "2-digit" })}
                </Text>
              </View>
            );
          }}
        />
      )}
      {err ? <Text style={styles.err} testID="chat-error">{err}</Text> : null}
      <View style={[styles.composer, { paddingBottom: Math.max(insets.bottom, spacing.md) }]}>
        <TextInput
          testID="chat-input"
          value={text}
          onChangeText={setText}
          placeholder={placeholder}
          placeholderTextColor={colors.muted}
          multiline
          style={styles.input}
          onSubmitEditing={Platform.OS === "web" ? () => onSend() : undefined}
        />
        <Pressable
          testID="chat-send-btn"
          onPress={() => onSend()}
          disabled={!text.trim() || sending}
          style={[styles.send, (!text.trim() || sending) && { opacity: 0.4 }]}
        >
          {sending ? <ActivityIndicator color={colors.onBrandPrimary} /> : <FeatherIcon name="send" size={18} color={colors.onBrandPrimary} />}
        </Pressable>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  empty: { flex: 1, alignItems: "center", justifyContent: "center", gap: spacing.md, paddingVertical: spacing["2xl"] },
  emptyText: { color: colors.muted, fontSize: 14, textAlign: "center", lineHeight: 20, paddingHorizontal: spacing.xl },
  suggestion: { borderWidth: 1, borderColor: colors.borderStrong, borderRadius: radius.pill, paddingHorizontal: spacing.lg, minHeight: 44, justifyContent: "center" },
  suggestionText: { color: colors.onSurfaceSecondary, fontSize: 13 },
  bubbleWrap: { maxWidth: "82%", gap: 2 },
  left: { alignSelf: "flex-start" },
  right: { alignSelf: "flex-end", alignItems: "flex-end" },
  sender: { color: colors.brandPrimary, fontSize: 11, fontWeight: "700", marginLeft: 4 },
  bubble: { borderRadius: radius.lg, paddingHorizontal: spacing.md, paddingVertical: 10 },
  bubbleMe: { backgroundColor: colors.brandPrimary, borderBottomRightRadius: 4 },
  bubbleThem: { backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border, borderBottomLeftRadius: 4 },
  msg: { color: colors.onSurface, fontSize: 15, lineHeight: 21 },
  time: { color: colors.muted, fontSize: 10, marginHorizontal: 4 },
  err: { color: colors.error, fontSize: 12, paddingHorizontal: spacing.lg },
  composer: {
    flexDirection: "row", alignItems: "flex-end", gap: spacing.sm, paddingHorizontal: spacing.lg, paddingTop: spacing.sm,
    borderTopWidth: 1, borderTopColor: colors.border, backgroundColor: colors.surface,
  },
  input: {
    flex: 1, maxHeight: 120, minHeight: 44, backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg,
    borderWidth: 1, borderColor: colors.border, paddingHorizontal: spacing.lg, paddingTop: 12, paddingBottom: 12,
    color: colors.onSurface, fontSize: 15,
  },
  send: { width: 44, height: 44, borderRadius: 22, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center" },
});
