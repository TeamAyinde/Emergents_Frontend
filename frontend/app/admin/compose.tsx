import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useEffect, useState } from "react";
import { Pressable, StyleSheet, Switch, Text, TextInput, View } from "react-native";
import { KeyboardAwareScrollView } from "react-native-keyboard-controller";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import FeatherIcon from "@react-native-vector-icons/feather";

import { api, Article } from "@/src/api";
import { colors, radius, spacing } from "@/src/theme";
import { LuxButton } from "@/src/ui";

const CATS: Article["category"][] = ["nightlife", "travel", "luxury"];
const COVERS: Record<Article["category"], string> = {
  nightlife: "https://images.unsplash.com/photo-1545128485-c400e7702796?w=1400&q=80",
  travel: "https://images.unsplash.com/photo-1540541338287-41700207dee6?w=1400&q=80",
  luxury: "https://images.unsplash.com/photo-1567899378494-47b22a2ae96a?w=1400&q=80",
};

export default function Compose() {
  const { id } = useLocalSearchParams<{ id?: string }>();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const qc = useQueryClient();
  const [topic, setTopic] = useState("");
  const [category, setCategory] = useState<Article["category"]>("nightlife");
  const [title, setTitle] = useState("");
  const [summary, setSummary] = useState("");
  const [body, setBody] = useState("");
  const [cover, setCover] = useState(COVERS.nightlife);
  const [published, setPublished] = useState(true);
  const [drafting, setDrafting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  const { data: existing } = useQuery({
    queryKey: ["admin-articles"],
    queryFn: () => api.adminArticles(),
    enabled: !!id,
  });
  useEffect(() => {
    const a = existing?.find((x) => x.id === id);
    if (!a) return;
    setCategory(a.category);
    setTitle(a.title);
    setSummary(a.summary);
    setBody(a.body);
    setCover(a.cover_image);
    setPublished(a.published);
  }, [existing, id]);

  async function onDraft() {
    if (topic.trim().length < 3) {
      setMsg({ ok: false, text: "Type a topic first" });
      return;
    }
    setMsg(null);
    setDrafting(true);
    try {
      const full = await api.streamDraft(topic.trim(), category, (text) => {
        const lines = text.replace("[[DRAFT_ERROR]]", "").split("\n");
        setTitle(lines[0]?.trim() ?? "");
        setSummary(lines[1]?.trim() ?? "");
        setBody(lines.slice(2).join("\n").trim());
      });
      if (full.includes("[[DRAFT_ERROR]]")) setMsg({ ok: false, text: "The AI stopped early. Edit the text or try again." });
    } catch (e) {
      setMsg({ ok: false, text: e instanceof Error ? e.message : "Draft failed" });
    } finally {
      setDrafting(false);
    }
  }

  async function onSave() {
    if (!title.trim() || !body.trim()) {
      setMsg({ ok: false, text: "Title and article text are required" });
      return;
    }
    setSaving(true);
    setMsg(null);
    try {
      const payload = { title: title.trim(), category, cover_image: cover.trim(), summary: summary.trim(), body: body.trim(), published };
      if (id) await api.updateArticle(id, payload);
      else {
        const created = await api.createArticle(payload);
        router.setParams({ id: created.id });
      }
      qc.invalidateQueries({ queryKey: ["admin-articles"] });
      qc.invalidateQueries({ queryKey: ["journal"] });
      setMsg({ ok: true, text: published ? "Published to the Journal." : "Saved as draft." });
    } catch (e) {
      setMsg({ ok: false, text: e instanceof Error ? e.message : "Save failed" });
    } finally {
      setSaving(false);
    }
  }

  return (
    <View style={styles.root}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.md }]}>
        <Pressable testID="compose-back" onPress={() => router.back()} style={styles.iconBtn}>
          <FeatherIcon name="chevron-left" size={22} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.headerTitle}>{id ? "Edit issue" : "New issue"}</Text>
        <View style={{ width: 40 }} />
      </View>
      <KeyboardAwareScrollView
        bottomOffset={24}
        keyboardShouldPersistTaps="handled"
        contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + spacing["2xl"], gap: spacing.md }}
      >
        <Text style={styles.label}>Category</Text>
        <View style={styles.cats}>
          {CATS.map((c) => (
            <Pressable
              key={c}
              testID={`compose-cat-${c}`}
              onPress={() => {
                setCategory(c);
                if (!id) setCover(COVERS[c]);
              }}
              style={[styles.cat, category === c && styles.catOn]}
            >
              <Text style={[styles.catText, category === c && styles.catTextOn]}>{c[0].toUpperCase() + c.slice(1)}</Text>
            </Pressable>
          ))}
        </View>

        <View style={styles.aiCard}>
          <Text style={styles.aiTitle}>Write with AI</Text>
          <TextInput
            testID="compose-topic"
            value={topic}
            onChangeText={setTopic}
            placeholder="e.g. Top 5 rooftop bars in LA this summer"
            placeholderTextColor={colors.muted}
            style={styles.input}
          />
          <LuxButton testID="compose-draft-btn" label={drafting ? "Writing…" : "Draft article"} onPress={onDraft} loading={drafting} />
        </View>

        <Text style={styles.label}>Title</Text>
        <TextInput testID="compose-title" value={title} onChangeText={setTitle} placeholderTextColor={colors.muted} placeholder="Headline" style={styles.input} />
        <Text style={styles.label}>Summary</Text>
        <TextInput testID="compose-summary" value={summary} onChangeText={setSummary} placeholderTextColor={colors.muted} placeholder="One line teaser" style={styles.input} />
        <Text style={styles.label}>Cover image link</Text>
        <TextInput testID="compose-cover" value={cover} onChangeText={setCover} autoCapitalize="none" style={styles.input} />
        <Text style={styles.label}>Article</Text>
        <TextInput
          testID="compose-body"
          value={body}
          onChangeText={setBody}
          multiline
          placeholder="Write or generate your story…"
          placeholderTextColor={colors.muted}
          style={[styles.input, { minHeight: 240, textAlignVertical: "top" }]}
        />
        <View style={styles.pubRow}>
          <Text style={styles.pubText}>Publish to members now</Text>
          <Switch
            testID="compose-published"
            value={published}
            onValueChange={setPublished}
            trackColor={{ true: colors.brandPrimary, false: colors.surfaceTertiary }}
          />
        </View>
        {msg ? <Text testID="compose-msg" style={{ color: msg.ok ? colors.success : colors.error }}>{msg.text}</Text> : null}
        <LuxButton testID="compose-save-btn" label={saving ? "Saving…" : published ? "Publish" : "Save draft"} onPress={onSave} loading={saving} />
      </KeyboardAwareScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.lg, paddingBottom: spacing.sm },
  headerTitle: { color: colors.onSurface, fontSize: 17, fontWeight: "700" },
  iconBtn: {
    width: 40, height: 40, borderRadius: 20, backgroundColor: colors.surfaceSecondary,
    borderWidth: 1, borderColor: colors.border, alignItems: "center", justifyContent: "center",
  },
  label: { color: colors.muted, fontSize: 12, letterSpacing: 1, textTransform: "uppercase", marginTop: spacing.xs },
  cats: { flexDirection: "row", gap: spacing.sm },
  cat: { flex: 1, height: 44, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary, alignItems: "center", justifyContent: "center" },
  catOn: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  catText: { color: colors.onSurfaceSecondary, fontWeight: "700" },
  catTextOn: { color: colors.onBrandPrimary },
  aiCard: { backgroundColor: colors.brandTertiary, borderRadius: radius.lg, padding: spacing.lg, gap: spacing.md, borderWidth: 1, borderColor: colors.brandPrimary },
  aiTitle: { color: colors.onBrandTertiary, fontSize: 16, fontWeight: "800" },
  input: {
    backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md,
    paddingHorizontal: spacing.lg, paddingVertical: 14, color: colors.onSurface, fontSize: 15,
  },
  pubRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", paddingVertical: spacing.sm },
  pubText: { color: colors.onSurface, fontSize: 15 },
});
