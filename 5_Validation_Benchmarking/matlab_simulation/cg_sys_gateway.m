function [a_mrm, gwp_out, lk_on, y_ref, park_out, alive_lost, reject, nrej_out] = cg_sys_gateway(t, hf, att, v, pv)
% ACTUATOR GATEWAY: the trusted boundary in front of the actuators.
%   Accepts a frame only if (authenticated AND fresh) AND phase order plausible AND
%   -4 <= decel <= 0. Host frames double as alive signal (300 ms timeout).
%   Host lost: nothing is actuated, unless a manoeuvre is already under way
%   (phase >= pv(11)), in which case the gateway completes the stop on its own.
Ts = 0.01;  JERK = 5;
persistent gwp a_out t_ok t_ph2 last_dec park nrej
if isempty(gwp)
    gwp = 0;  a_out = 0;  t_ok = 0;  t_ph2 = -1;  last_dec = 0;  park = false;  nrej = 0;
end
fr = zeros(5, 2);                             % column 1 host, column 2 attacker
fr(:, 1) = hf(1:5);
fr(:, 2) = att(1:5);
reject = 0;
for k = 1:2
    f = fr(:, k);
    if f(1) > 0.5
        ph = round(f(2));  dc = f(3);
        ok_auth = (f(4) > 0.5) && (f(5) > 0.5);
        ok_ph = (ph == gwp) || (ph == gwp + 1) || (ph == 0 && (gwp == 1 || gwp == 2));   % same table as the Python gateway
        ok_dc = (dc <= 0) && (dc >= -4);
        if ok_auth && ok_ph && ok_dc
            if ph ~= gwp
                gwp = ph;
                if ph == 2, t_ph2 = t; end
            end
            last_dec = dc;
            if k == 1, t_ok = t; end
        else
            reject = 1;  nrej = nrej + 1;
        end
    end
end
alive_lost = double((t - t_ok) > 0.3);

tgt = 0;
if alive_lost < 0.5
    if gwp >= 3, tgt = last_dec; end
else
    if gwp >= pv(11)
        if gwp >= 3
            tgt = min(last_dec, pv(7));
        elseif gwp == 2 && (t - t_ph2) >= (pv(6) - pv(13))
            gwp = 3;  tgt = pv(7);            % gateway-owned fallback timer
        end
    end
end
% taper the deceleration near standstill (no artificial stop jolt) and ramp it out once parked
if tgt < 0, tgt = tgt * min(1, 0.25 + max(v, 0)/2.0); end
if park, tgt = 0; end
da = max(-JERK*Ts, min(JERK*Ts, tgt - a_out));
a_out = a_out + da;
if gwp >= 3 && v < 0.1, park = true; end

a_mrm = a_out;                                % plant holds v = 0 while parked
gwp_out = gwp;
lk_on = double(pv(5) > 1.5 || (pv(5) > 0.5 && gwp >= 1));
y_ref = pv(12) * double(gwp >= 2);            % start the move to the shoulder at HAZARD
park_out = double(park);
nrej_out = nrej;
end

