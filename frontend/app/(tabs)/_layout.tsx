import { Tabs } from "expo-router";
import FeatherIcon from "@react-native-vector-icons/feather";
import { Platform } from "react-native";

import { colors } from "@/src/theme";

export default function TabsLayout() {
  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: colors.brandPrimary,
        tabBarInactiveTintColor: colors.muted,
        tabBarStyle: {
          backgroundColor: colors.surface,
          borderTopColor: colors.border,
          borderTopWidth: 0.5,
          ...(Platform.OS === "web" ? { height: 64 } : {}),
        },
        tabBarItemStyle: { alignSelf: "center" },
        tabBarLabelStyle: { fontSize: 11, fontWeight: "600", letterSpacing: 0.4 },
      }}
    >
      <Tabs.Screen
        name="index"
        options={{
          title: "Home",
          tabBarIcon: ({ color, size }) => <FeatherIcon name="home" color={color} size={size} />,
        }}
      />
      <Tabs.Screen
        name="promote"
        options={{
          title: "Promote",
          tabBarIcon: ({ color, size }) => <FeatherIcon name="trending-up" color={color} size={size} />,
        }}
      />
      <Tabs.Screen
        name="venues"
        options={{
          title: "Explore",
          tabBarIcon: ({ color, size }) => <FeatherIcon name="compass" color={color} size={size} />,
        }}
      />
      <Tabs.Screen
        name="profile"
        options={{
          title: "Profile",
          tabBarIcon: ({ color, size }) => <FeatherIcon name="user" color={color} size={size} />,
        }}
      />
    </Tabs>
  );
}
