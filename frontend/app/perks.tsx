import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Image } from "expo-image";
import { useRouter } from "expo-router";
import { ActivityIndicator, FlatList, Pressable, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import FeatherIcon from "@react-native-vector-icons/feather";

import { api, Perk } from "@/src/api";
import { Level, LEVEL_INFO, LevelBadge } from "@/src/levels";
import { colors, radius, spacing } from "@/src/theme";

export default function Perks() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({ queryKey: ["perks"], queryFn: () => api.perks() });
  const claim = useMutation({
    mutationFn: (id: string) => api.claimPerk(id),
    onSuccess: (p) => qc.setQueryData<Perk[]>(["perks"], (old) => old?.map((x) => (x.id === p.id ? p : x))),
  });

  return (
    <View style={styles.root}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.md }]}>
        <Pressable testID="perks-back" onPress={() => router.back()} style={styles.iconBtn}>
          <FeatherIcon name="chevron-left" size={22} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.title}>Members perks</Text>
        <View style={{ width: 44 }} />
      </View>
      {isLoading ? (
        <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: spacing["2xl"] }} />
      ) : (
        <FlatList
          data={data ?? []}
          keyExtractor={(p) => p.id}
          contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + spacing.xl, gap: spacing.md }}
          renderItem={({ item }) => (
            <View style={[styles.card, item.locked && { opacity: 0.7 }]} testID={`perk-${item.id}`}>
              <Image source={item.image_url} style={styles.img} contentFit="cover" />
              <LevelBadge level={item.min_level} floating />
              <View style={styles.body}>
                <Text style={styles.partner}>{item.partner_name.toUpperCase()}</Text>
                <Text style={styles.perkTitle}>{item.title}</Text>
                <Text style={styles.desc}>{item.description}</Text>
                {item.claimed ? (
                  <View style={styles.code} testID={`perk-code-${item.id}`}>
                    <Text style={styles.codeLabel}>SHOW THIS CODE</Text>
                    <Text style={styles.codeText}>{item.code}</Text>
                  </View>
                ) : item.locked ? (
                  <Pressable testID={`perk-unlock-${item.id}`} onPress={() => router.push("/membership")} style={styles.btnGhost}>
                    <Text style={styles.btnGhostText}>Unlock with {LEVEL_INFO[item.min_level as Level].label}</Text>
                  </Pressable>
                ) : (
                  <Pressable testID={`perk-claim-${item.id}`} disabled={claim.isPending} onPress={() => claim.mutate(item.id)} style={styles.btn}>
                    <Text style={styles.btnText}>Claim perk</Text>
                  </Pressable>
                )}
              </View>
            </View>
          )}
        />
      )}
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
  card: { borderRadius: radius.lg, overflow: "hidden", backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border },
  img: { width: "100%", height: 120 },
  body: { padding: spacing.lg, gap: 6 },
  partner: { color: colors.brandPrimary, fontSize: 10, letterSpacing: 2, fontWeight: "800" },
  perkTitle: { color: colors.onSurface, fontSize: 18, fontWeight: "800" },
  desc: { color: colors.muted, fontSize: 13, lineHeight: 19 },
  btn: { marginTop: spacing.sm, height: 44, borderRadius: radius.pill, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center" },
  btnText: { color: colors.onBrandPrimary, fontWeight: "800" },
  btnGhost: { marginTop: spacing.sm, height: 44, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.borderStrong, alignItems: "center", justifyContent: "center" },
  btnGhostText: { color: colors.onSurface, fontWeight: "700" },
  code: { marginTop: spacing.sm, borderRadius: radius.md, borderWidth: 1, borderStyle: "dashed", borderColor: colors.brandPrimary, padding: spacing.md, alignItems: "center" },
  codeLabel: { color: colors.muted, fontSize: 10, letterSpacing: 2, fontWeight: "700" },
  codeText: { color: colors.brandPrimary, fontSize: 22, fontWeight: "800", letterSpacing: 3 },
});
