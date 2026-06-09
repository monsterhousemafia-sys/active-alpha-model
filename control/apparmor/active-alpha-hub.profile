# Optional — sudo apparmor_parser -r /home/machinax7/active_alpha_model/control/apparmor/active-alpha-hub.profile
#include <tunables/global>
profile active-alpha-hub flags=(attach_disconnected) {
  /home/machinax7/active_alpha_model/.venv/bin/python3 mr,
  /home/machinax7/active_alpha_model/tools/preview_hub.py r,
  /home/machinax7/active_alpha_model/evidence/** rw,
  /home/machinax7/active_alpha_model/control/** r,
  network tcp port 17890,
  deny /home/*/.ssh/** r,
}
