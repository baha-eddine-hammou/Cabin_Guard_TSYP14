function [sc, info] = cg_dsd_scenario(o)
% CG_DSD_SCENARIO  Driving Scenario: 3-lane road (driving, driving, SHOULDER on the right), ego in lane 2, one follower.
%   The follower holds its speed until it reacts to the ego's braking (t_act + 0.3 s brake lights + tau), then brakes at af.
%   Its motion is scripted in the scenario (DSD actors do not react by themselves) - this is a stated limitation.
o = cg_dsd_opts(o);
ds = 10;  lw = 3.6;
L = o.s_ego + max(o.v0 * o.T * 1.15, 300) + 150;
n = ceil(L / ds) + 1;  s = (0:n-1)' * ds;
switch o.road
    case 'straight', kap = zeros(n, 1);
    case 'scurve',   kap = 0.004 * sin(2*pi*s/450);
    case 'random'
        rs = RandStream('mt19937ar', 'Seed', o.seed);  kap = zeros(n, 1);  i = 1;
        while i <= n
            len = ceil((60 + rand(rs) * 100) / ds);  k = 0;
            if rand(rs) > 0.3, k = (2*rand(rs) - 1) / o.Rmin; end
            kap(i:min(n, i+len-1)) = k;  i = i + len;
        end
        kap = conv(kap, ones(5, 1)/5, 'same');
    otherwise, error('Unknown road type %s.', o.road);
end
psi = zeros(n, 1);  x = zeros(n, 1);  y = zeros(n, 1);
for i = 1:n-1
    psi(i+1) = psi(i) + kap(i) * ds;
    x(i+1) = x(i) + ds * cos(psi(i) + 0.5*kap(i)*ds);
    y(i+1) = y(i) + ds * sin(psi(i) + 0.5*kap(i)*ds);
end
pts = [x y zeros(n, 1)];
% dense centre line (1 m) for metrics
sd = (0:1:s(end))';  xd = interp1(s, x, sd, 'pchip');  yd = interp1(s, y, sd, 'pchip');
hd = atan2(gradient(yd), gradient(xd));

sc = drivingScenario('SampleTime', 0.1, 'StopTime', o.T);
ls = lanespec(3, 'Width', lw, 'Type', [laneType('Driving') laneType('Driving') laneType('Shoulder')]);
road(sc, pts, 'Lanes', ls);
se = o.s_ego;  xe = interp1(sd, xd, se);  ye = interp1(sd, yd, se);  he = interp1(sd, hd, se);
vehicle(sc, 'ClassID', 1, 'Position', [xe ye 0], 'Yaw', rad2deg(he));          % actor 1 = ego (driven from the model)
% follower
sf0 = se - o.gap0;  xf = interp1(sd, xd, sf0);  yf = interp1(sd, yd, sf0);
tr = o.t_act + 0.3 + o.tau;
tg = (0:0.01:o.T + 20)';
vf = @(t) max(0, o.vf0 - o.af * max(0, t - tr));
v = vf(tg);  sfT = sf0 + cumtrapz(tg, v);
last = find(v > 0.3, 1, 'last');
idx = (s > sf0 + 1) & (s < sfT(last));
tw = interp1(sfT(1:last), tg(1:last), s(idx));
wp = [xf yf 0; pts(idx, :)];
sp = [vf(0); max(0.3, vf(tw))];
fol = vehicle(sc, 'ClassID', 1, 'Position', wp(1, :));
trajectory(fol, wp, sp);
info = struct('pts', pts, 's', s, 'sd', sd, 'xd', xd, 'yd', yd, 'hd', hd, 'lw', lw, 'x0', xe, 'y0', ye, 'psi0', he, ...
              'vf', vf, 'tr', tr, 'sf0', sf0, 'opts', o);
end
