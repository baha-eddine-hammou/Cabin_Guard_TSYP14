function lam = cg_sys_detector(t, pv, dp)
% SURROGATE OF THE AI DETECTORS (replace with the real network output when it is connected).
%   Gives the log-evidence the Host expects: 4 branches (cardiac, vision, IMU/motion, seat/grip) x 2 classes (syncope, seizure).
%   lam = [S1 Z1 S2 Z2 S3 Z3 S4 Z4]'
%   pv(1) = incapacitation onset, pv(2) = event (0 none, 1 syncope, 2 seizure)
%   dp(1) = detector delay [s] after the onset, dp(2) = ramp time [s]
%   dp(3:5) = false alarm: start [s], duration [s], mode (0 none, 1 camera branches only, 2 all branches)
lam = zeros(8, 1);
ev = pv(2);  ton = pv(1);
dly = dp(1);  ramp = max(dp(2), 0.1);
if ev ~= 0 && t >= ton + dly
    g = min(1, (t - ton - dly) / ramp);
    k = min(max(round(ev), 1), 2);
    for b = 1:4
        lam(2*b - 2 + k) = 4 * g;
        lam(2*b - 2 + 3 - k) = -2 * g;
    end
end
if dp(5) > 0.5 && t >= dp(3) && t < dp(3) + dp(4)
    nb = 2;
    if dp(5) > 1.5, nb = 4; end
    for b = 1:nb
        lam(2*b - 1) = 4;  lam(2*b) = -2;
    end
end
end
