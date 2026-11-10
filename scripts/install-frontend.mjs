#!/usr/bin/env node
// Installiert die Frontend-Abhängigkeiten aus frontend/package-lock.json.
//
// Der Aufruf erfolgt über den postinstall-Hook im Wurzel-package.json, damit
// "npm install" am Repo-Root auch in Umgebungen funktioniert, die nur ein
// Node-Projekt im Wurzelverzeichnis erkennen. npm reicht eine globale
// allow-scripts-Konfiguration an verschachtelte Installationen weiter, wo das
// Flag abgelehnt wird; deshalb wird die Variable für den Kindprozess entfernt.
import { spawnSync } from "node:child_process";

const env = { ...process.env };
delete env.npm_config_allow_scripts;

const result = spawnSync(
  "npm",
  ["--prefix", "frontend", "ci", "--no-audit", "--no-fund"],
  { stdio: "inherit", env, shell: process.platform === "win32" },
);

if (result.error) {
  console.error(`Frontend-Abhängigkeiten konnten nicht installiert werden: ${result.error.message}`);
}

process.exit(result.status ?? 1);
