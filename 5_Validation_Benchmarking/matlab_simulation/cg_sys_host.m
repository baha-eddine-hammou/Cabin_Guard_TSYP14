function [hf, F, alert, dmode, Pmax, cls, ecall, warn, state] = cg_sys_host(t, lam, avail, tau, grip, clonic, brake_pedal, v, pv)
% EDGE HOST: bounded-evidence fusion (Eqs. 3-6), 2 s verification, two-sensor rule,
% camera interlock, degraded modes and the MRM state machine. Detector runs at 10 Hz.
%   state: 0 NORMAL, 1 ALERT, 2 HAZARD, 3 BRAKE, 4 STANDSTILL
%   dmode: 0 nominal, 1 camera lost, 2 IMU lost, 3 <2 sensors (no MRM), 4 seat lost
%   hf   : command frame [send; phase; decel_req; mac_ok; fresh_ok] (crypto outcome is
%          abstracted: the SecOC MAC/freshness are unit-tested in the Python code)
c = 3;  GAM = 0.85;  NW = 20;  TVER = 2;
lp = log([0.8 0.1 0.1]);                     % operational prior N, S, Z

persistent n buf vcnt st t_a cool dist_until Pm cl md wr last_ie
if isempty(n)
    n = 0;  buf = zeros(NW, 8);  vcnt = 0;  st = 0;  t_a = 0;
    cool = -1;  dist_until = -1;  Pm = 0;  cl = 0;  md = 0;  wr = 0;  last_ie = 0;
end
lam = lam(:);  avail = avail(:);
n = n + 1;
tick = (mod(n, 10) == 0);

if tick
    % cross-sensor interlock: camera claims an event while the wheel shows an upright,
    % steering driver -> distrust the camera for 10 s
    if max(lam(1:4)) >= 1 && tau > 1 && grip < 0.5 && clonic < 0.5
        dist_until = t + 10;
    end
    cam_ok = (avail(1) > 0.5) && (t >= dist_until);
    imu_ok = avail(2) > 0.5;
    seat_ok = avail(3) > 0.5;

    % Eq. (4): bounded evidence per branch (shifts both event classes together)
    lb = zeros(8, 1);
    for b = 1:4
        l2 = lam(2*b-1:2*b);
        m = max(0, max(l2) - c);
        lb(2*b-1:2*b) = max(-c, l2 - m);
    end
    bav = [cam_ok; cam_ok; imu_ok; seat_ok];  % cardiac+vision need camera
    for b = 1:4
        if ~bav(b), lb(2*b-1:2*b) = 0; end
    end
    buf = [buf(2:end, :); lb'];
    lbar = mean(buf, 1)';                     % average over last W = 2 s

    % Eq. (5): fused posterior
    sS = lbar(1) + lbar(3) + lbar(5) + lbar(7);
    sZ = lbar(2) + lbar(4) + lbar(6) + lbar(8);
    lg = [lp(1), lp(2) + sS, lp(3) + sZ];
    lg = lg - max(lg);
    p = exp(lg) / sum(exp(lg));
    [pe, ie] = max(p(2:3));

    % two physical sensors must agree (camera counts once)
    cols = [1 3 5 7] + (ie - 1);
    camAg = (lbar(cols(1)) >= 1) || (lbar(cols(2)) >= 1);
    nag = double(camAg) + double(lbar(cols(3)) >= 1) + double(lbar(cols(4)) >= 1);

    nav = double(cam_ok) + double(imu_ok) + double(seat_ok);
    if nav < 2
        md = 3;
    elseif avail(1) <= 0.5
        md = 1;
    elseif avail(2) <= 0.5
        md = 2;
    elseif avail(3) <= 0.5
        md = 4;
    else
        md = 0;
    end

    if ie ~= last_ie, vcnt = 0; end
    last_ie = ie;
    if pe >= GAM && nag >= 2 && t >= cool
        vcnt = vcnt + 1;
    else
        vcnt = 0;
    end
    cand = (vcnt >= TVER/0.1) && (nav >= 2) && (pv(15) > 0.5);
    wr = double((nav < 2) && (pe >= GAM));    % warn only, MRM forbidden
    Pm = pe;  cl = ie;

    % MRM state machine (design values of the paper)
    switch st
        case 0
            if cand, st = 1; t_a = t; end
        case 1
            cancel = (brake_pedal > 0.5) || (abs(tau) > 4 && clonic < 0.5 && grip < 1.5);
            if cancel
                st = 0;  vcnt = 0;  cool = t + 10;  buf(:) = 0;
            elseif t - t_a >= pv(13)
                st = 2;
            end
        case 2
            if t - t_a >= pv(6), st = 3; end
        case 3
            if v < 0.3, st = 4; end
    end
end

hung = (pv(8) == 4) && (t >= pv(9));          % host hang: goes silent
send = double(tick && pv(15) > 0.5 && ~hung);
dec = 0;
if st >= 3, dec = pv(7); end
hf = [send; st; dec; 1; 1];
F = double(st >= 1);
alert = double(st == 1);
dmode = md;
Pmax = Pm;
cls = cl * double(st >= 1);
ecall = double(st >= 2);                      % call placed when the alert goes unanswered
warn = wr;
state = st;
end

