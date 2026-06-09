#!/usr/bin/env bash
# Repair incomplete Ubuntu OOBE (username without password/home).
set -euo pipefail

USER_NAME="${1:-monst}"

mkdir -p "/home/${USER_NAME}"
chown "${USER_NAME}:${USER_NAME}" "/home/${USER_NAME}"
usermod -d "/home/${USER_NAME}" "${USER_NAME}" || true
usermod -aG sudo "${USER_NAME}" 2>/dev/null || usermod -aG wheel "${USER_NAME}" 2>/dev/null || true

# No password required inside WSL (common for dev boxes).
passwd -d "${USER_NAME}" || true
SUDOERS="/etc/sudoers.d/${USER_NAME}"
echo "${USER_NAME} ALL=(ALL) NOPASSWD:ALL" > "${SUDOERS}"
chmod 440 "${SUDOERS}"

WSL_CONF="/etc/wsl.conf"
if [[ -f "${WSL_CONF}" ]] && grep -q '^default=' "${WSL_CONF}"; then
  sed -i "s/^default=.*/default=${USER_NAME}/" "${WSL_CONF}"
elif [[ -f "${WSL_CONF}" ]] && grep -q '^\[user\]' "${WSL_CONF}"; then
  printf 'default=%s\n' "${USER_NAME}" >> "${WSL_CONF}"
else
  printf '[user]\ndefault=%s\n' "${USER_NAME}" >> "${WSL_CONF}"
fi

if [[ -d /root/active_alpha_model ]]; then
  rsync -a /root/active_alpha_model/ "/home/${USER_NAME}/active_alpha_model/"
  chown -R "${USER_NAME}:${USER_NAME}" "/home/${USER_NAME}/active_alpha_model"
fi

echo "fixed user=${USER_NAME}"
echo "home=$(getent passwd "${USER_NAME}" | cut -d: -f6)"
echo "passwd_status=$(passwd -S "${USER_NAME}" 2>/dev/null || echo unknown)"
echo "wsl_conf_default=$(grep -E '^default=' "${WSL_CONF}" || true)"
