function [lam_f, avail, att, cell_up, sms_up] = cg_sys_faults(t, lam, pv)
% FAULT / ATTACK INJECTOR
%   fault id (pv(8)), starting at t_fault (pv(9)):
%    0 none            1 camera lost      2 IMU lost         3 seat sensor lost
%    4 host hang (handled in Host + Gateway)
%    5 forged command (bad MAC)           6 replayed command (stale freshness)
%    7 valid MAC but implausible decel    8 cellular down 60 s
%    9 camera blinded/spoofed (no pulse + closed eyes)
%   10 all bearers down 60 s             11 valid MAC but phase skipped
%   att = attacker frame [present; phase; decel; mac_ok; fresh_ok] at 10 Hz
lam_f = lam(:);
avail = [1; 1; 1];
att = zeros(5, 1);
cell_up = 1;  sms_up = 1;
fid = pv(8);  tf = pv(9);
on = (t >= tf);
tick = abs(t/0.1 - round(t/0.1)) < 1e-6;
switch fid
    case 1
        if on, avail(1) = 0; end
    case 2
        if on, avail(2) = 0; end
    case 3
        if on, avail(3) = 0; end
    case 5
        if on && tick, att = [1; 3; -4; 0; 1]; end
    case 6
        if on && tick, att = [1; 3; -3; 1; 0]; end
    case 7
        if on && tick, att = [1; 0; -6; 1; 1]; end
    case 8
        if on && t < tf + 60, cell_up = 0; end
    case 9
        if on, lam_f(1) = 6; lam_f(3) = 6; end
    case 10
        if on && t < tf + 60, cell_up = 0; sms_up = 0; end
    case 11
        if on && tick, att = [1; 3; -3; 1; 1]; end
end
end

