import React from "react";
import { Platform, Pressable, StyleSheet, Text, View, ViewStyle } from "react-native";
import { LinearGradient } from "expo-linear-gradient";

import { colors, radius, spacing } from "./theme";

type Variant = "primary" | "secondary" | "ghost" | "danger";

export function LuxButton({
  label,
  onPress,
  variant = "primary",
  disabled = false,
  loading = false,
  testID,
  icon,
  style,
}: {
  label: string;
  onPress: () => void;
  variant?: Variant;
  disabled?: boolean;
  loading?: boolean;
  testID?: string;
  icon?: React.ReactNode;
  style?: ViewStyle;
}) {
  const content = (
    <View style={styles.inner}>
      {icon}
      <Text
        style={[
          styles.label,
          variant === "secondary" && { color: colors.onSurface },
          variant === "ghost" && { color: colors.brandPrimary },
          variant === "danger" && { color: colors.onBrandSecondary },
        ]}
      >
        {loading ? "…" : label}
      </Text>
    </View>
  );

  if (variant === "primary") {
    return (
      <Pressable
        testID={testID}
        onPress={onPress}
        disabled={disabled || loading}
        style={[styles.base, disabled && styles.disabled, style]}
      >
        <LinearGradient
          colors={["#F5B041", "#E5A93C", "#B8731D"]}
          start={{ x: 0, y: 0 }}
          end={{ x: 1, y: 1 }}
          style={styles.grad}
        >
          <Text style={styles.label}>{loading ? "…" : label}</Text>
          {icon ? <View style={{ marginLeft: 8 }}>{icon}</View> : null}
        </LinearGradient>
      </Pressable>
    );
  }

  const bg =
    variant === "danger"
      ? colors.brandSecondary
      : variant === "ghost"
        ? "transparent"
        : colors.surfaceTertiary;
  const borderColor = variant === "ghost" ? colors.borderStrong : "transparent";
  return (
    <Pressable
      testID={testID}
      onPress={onPress}
      disabled={disabled || loading}
      style={[
        styles.base,
        { backgroundColor: bg, borderColor, borderWidth: variant === "ghost" ? 1 : 0 },
        disabled && styles.disabled,
        style,
      ]}
    >
      {content}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  base: {
    height: 52,
    borderRadius: radius.pill,
    overflow: "hidden",
    justifyContent: "center",
    alignItems: "center",
  },
  grad: {
    flex: 1,
    width: "100%",
    paddingHorizontal: spacing.xl,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
  },
  inner: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: spacing.xl,
    gap: spacing.sm,
  },
  label: {
    color: "#1A0A00",
    fontSize: 15,
    fontWeight: "700",
    letterSpacing: 0.3,
  },
  disabled: { opacity: 0.5 },
});
export function GlassCard({
  children,
  style,
}: {
  children: React.ReactNode;
  style?: ViewStyle;
}) {
  return (
    <View
      style={[
        {
          backgroundColor: Platform.OS === "web" ? "rgba(24,24,27,0.75)" : "rgba(24,24,27,0.6)",
          borderWidth: 1,
          borderColor: colors.border,
          borderRadius: radius.lg,
          padding: spacing.lg,
        },
        style,
      ]}
    >
      {children}
    </View>
  );
}
