import { Config } from "@remotion/cli/config";

// Use SwiftShader (software OpenGL) — required for VPS / headless Linux servers with no GPU.
// Switch to "angle" if rendering locally on a machine with Chrome + GPU.
Config.setChromiumOpenGlRenderer("swiftshader");

// Disable sandbox — necessary on most Linux VPS environments.
Config.setChromiumDisableWebSecurity(false);
Config.overrideWebpackConfig((config) => config);
