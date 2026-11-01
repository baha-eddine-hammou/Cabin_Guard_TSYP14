function [sc, info] = cg_auto_scene(o)
% CG_AUTO_SCENE  Random Driving Scenario for the autonomous take-over tests.
%   type 'highway' : 3 driving lanes (+ shoulder 75 %), 20-28 m/s, gentle curves, traffic in all lanes
%   type 'rural'   : 2 driving lanes (+ shoulder 60 %), 13-22 m/s, tight curves, sometimes a pedestrian
%   type 'city'    : 2 driving lanes + parking lane with parked cars, 8-14 m/s, crossing pedestrians
%   Possible content (random): slower / stopped / suddenly braking car ahead, follower that brakes late,
%   cars in the other lanes (blind spot), disabled car on the shoulder, pedestrians crossing the road.
%   Every actor other than the ego follows a scripted path (DSD actors do not react to the ego) - stated limitation.
%   The ego is actor 1; it is driven by the Simulink model.
o = cg_auto_opts(o);
ti = find(strcmp(o.type, {'highway', 'rural', 'city'}));
if isempty(ti), error('Unknown scene type %s.', o.type); end
rs = RandStream('mt19937ar', 'Seed', o.seed + 7919 * ti);
U = @(a, b) a + (b - a) * rand(rs);
switch o.type
    case 'highway', nd = 3; lw = 3.6; edgeType = 'Shoulder'; hasEdge = rand(rs) < 0.75; v0 = U(20, 28); Rmin = U(400, 900);
    case 'rural',   nd = 2; lw = 3.3; edgeType = 'Shoulder'; hasEdge = rand(rs) < 0.60; v0 = U(13, 22); Rmin = U(120, 300);
    case 'city',    nd = 2; lw = 3.2; edgeType = 'Parking';  hasEdge = true;            v0 = U(8, 14);  Rmin = U(250, 600);
end
if ~isempty(o.v0), v0 = o.v0; end
nl = nd + double(hasEdge);
cen = ((nl + 1) / 2 - (1:nl)) * lw;                  % lane centre offsets from the road centre line (left positive)
egoLane = 1 + floor(rand(rs) * nd);
if ~strcmp(o.content, 'random'), egoLane = nd; end        % fixed tests: rightmost driving lane (the edge lane is next to it)
ta = o.t_act;
T = o.T;  if isempty(T), T = ceil(ta + v0 / 3.0 + 3); end

%% road centre line
ds = 10;  s_ego = 100;
L = s_ego + max(v0 * T * 1.15, 300) + 250;
n = ceil(L / ds) + 1;  s = (0:n-1)' * ds;
kap = zeros(n, 1);  i = 1;
while i <= n
    len = ceil((60 + rand(rs) * 120) / ds);  k = 0;
    if rand(rs) > 0.3, k = (2 * rand(rs) - 1) / Rmin; end
    kap(i:min(n, i + len - 1)) = k;  i = i + len;
end
kap = conv(kap, ones(5, 1) / 5, 'same');
psi = zeros(n, 1);  x = zeros(n, 1);  y = zeros(n, 1);
for i = 1:n-1
    psi(i+1) = psi(i) + kap(i) * ds;
    x(i+1) = x(i) + ds * cos(psi(i) + 0.5 * kap(i) * ds);
    y(i+1) = y(i) + ds * sin(psi(i) + 0.5 * kap(i) * ds);
end
pts = [x y zeros(n, 1)];
sd = (0:1:s(end))';  xd = interp1(s, x, sd, 'pchip');  yd = interp1(s, y, sd, 'pchip');
hd = unwrap(atan2(gradient(yd), gradient(xd)));
info = struct('pts', pts, 's', s, 'sd', sd, 'xd', xd, 'yd', yd, 'hd', hd, 'lw', lw, 'nl', nl, 'nd', nd, 'cen', cen, 'egoLane', egoLane, ...
              'hasEdge', hasEdge, 'type', o.type, 'v0', v0, 'T', T, 'egoID', 1, 'Rmin', Rmin, 's_ego', s_ego);

sc = drivingScenario('SampleTime', 0.1, 'StopTime', T);
lt = laneType('Driving');
for i = 2:nd, lt(i) = laneType('Driving'); end
if hasEdge
    try, lt(nl) = laneType(edgeType); catch, lt(nl) = laneType('Shoulder'); end
end
road(sc, pts, 'Lanes', lanespec(nl, 'Width', lw, 'Type', lt));

%% ego = actor 1 (driven from Simulink)
[xe, ye, he] = posAt(info, s_ego, cen(egoLane));
vehicle(sc, 'ClassID', 1, 'Position', [xe ye 0], 'Yaw', rad2deg(he));
info.x0 = xe;  info.y0 = ye;  info.psi0 = he;
info.clear_expected = (nl - egoLane + 0.5) * lw;     % ego lane centre to the right road edge

desc = {};  roles = {'ego'};
info.lead = 0;  info.follower = 0;  info.nped = 0;  info.nadj = 0;  info.nparked = 0;  info.disabled = 0;

rnd = strcmp(o.content, 'random');
if rnd
%% car ahead in the ego lane
if rand(rs) < 0.7
    kind = rand(rs);
    if kind < 0.45                                   % slower traffic
        gapT = U(25, 70);  vl = v0 * U(0.55, 0.92);  gap = gapT + (v0 - vl) * ta;      % gapT = gap at the moment the driver stops (before that the driver is driving: no collision allowed)
        addCar(sc, info, s_ego + gap, cen(egoLane), @(t) vl + 0 * t, T);  roles{end+1} = 'slow car ahead';
        info.lead = 1;  desc{end+1} = sprintf('slow car %.0f m ahead (%.0f m/s)', gap, vl);
    elseif kind < 0.70                               % stopped car / end of a queue
        sobj = s_ego + v0 * ta + v0^2 / (2 * 7) * U(1.0, 2.2) + 8;
        addCar(sc, info, sobj, cen(egoLane), @(t) 0 * t, T);  roles{end+1} = 'stopped car ahead';
        info.lead = 2;  desc{end+1} = sprintf('STOPPED car %.0f m ahead of the start', sobj - s_ego);
    else                                             % sudden braking
        gapT = U(25, 60);  vl = v0 * U(0.9, 1.0);  tb = U(ta, ta + 2);  ab = U(3, 7);  gap = gapT + (v0 - vl) * ta;
        addCar(sc, info, s_ego + gap, cen(egoLane), @(t) max(0, vl - ab * max(0, t - tb)), T);  roles{end+1} = 'braking car ahead';
        info.lead = 3;  desc{end+1} = sprintf('car %.0f m ahead brakes at %.1f m/s^2 at t=%.1f s', gap, ab, tb);
    end
end

%% follower in the ego lane
if rand(rs) < 0.6
    gapfT = U(10, 45);  vf0 = v0 * U(0.95, 1.08);  tau = U(1, 2.5);  af = U(3, 7);  tr = ta + 0.3 + tau;  gapf = gapfT + max(0, vf0 - v0) * ta;
    addCar(sc, info, s_ego - gapf, cen(egoLane), @(t) max(0, vf0 - af * max(0, t - tr)), T);  roles{end+1} = 'follower';
    info.follower = 1;  desc{end+1} = sprintf('follower %.0f m behind, reacts after %.1f s', gapf, tau + 0.3);
end

%% traffic in the other driving lanes
for k = 1:nd
    if k == egoLane, continue, end
    placed = [];
    for c = 1:floor(rand(rs) * 3)
        s0 = s_ego + U(-50, 80);  vc = v0 * U(0.75, 1.12);
        if any(abs(placed - s0) < 14), continue, end
        placed(end+1) = s0; %#ok<AGROW>
        addCar(sc, info, s0, cen(k), @(t) vc + 0 * t, T);  roles{end+1} = 'car in other lane';
        info.nadj = info.nadj + 1;
    end
end
if info.nadj > 0, desc{end+1} = sprintf('%d cars in other lanes', info.nadj); end

%% edge lane: disabled car on the shoulder / parked cars at the kerb
if hasEdge && strcmp(edgeType, 'Shoulder') && rand(rs) < 0.3
    sdis = s_ego + U(60, 220);
    addCar(sc, info, sdis, cen(nl), @(t) 0 * t, T);  roles{end+1} = 'disabled car on shoulder';
    info.disabled = 1;  desc{end+1} = sprintf('disabled car on the shoulder %.0f m ahead', sdis - s_ego);
end
if hasEdge && strcmp(edgeType, 'Parking')
    sp = s_ego - 20;
    while sp < s_ego + 300
        sp = sp + U(6.5, 10);
        if rand(rs) < 0.55
            addCar(sc, info, sp, cen(nl), @(t) 0 * t, T);  info.nparked = info.nparked + 1;  roles{end+1} = 'parked car';
        end
    end
    desc{end+1} = sprintf('%d parked cars', info.nparked);
end

%% pedestrians
switch o.type
    case 'city',  npd = (rand(rs) < 0.9) * (1 + floor(rand(rs) * 3));
    case 'rural', npd = double(rand(rs) < 0.3);
    otherwise,    npd = 0;
end
half = nl * lw / 2;
for k = 1:npd
    D = v0^2 / (2 * 7) * U(1.0, 2.2) + 10;
    sp = s_ego + v0 * ta + D;
    tc = ta + D / (0.75 * v0) + U(-0.5, 0.5);
    side = sign(randn(rs));  if side == 0, side = 1; end
    latS = side * (half + 1.2);  latE = -side * (half + 1.2);
    spd = U(1.1, 1.8);
    tstart = max(0, tc - abs(latS - cen(egoLane)) / spd);
    addPed(sc, info, sp, latS, latE, spd, tstart);  roles{end+1} = 'pedestrian';
    info.nped = info.nped + 1;
    desc{end+1} = sprintf('pedestrian crossing %.0f m ahead of the take-over point, enters the ego lane at about t=%.1f s', D, tc); %#ok<AGROW>
end
else
    % deterministic test content (to check the sensors and the decisions one at a time)
    switch o.content
        case 'stopped'
            sobj = s_ego + v0 * ta + v0^2 / (2 * 7) * 1.6 + 8;
            addCar(sc, info, sobj, cen(egoLane), @(t) 0 * t, T);  info.lead = 2;  roles{end+1} = 'stopped car ahead';
            desc{end+1} = sprintf('STOPPED car %.0f m ahead of the start', sobj - s_ego);
        case 'ped'
            D = v0^2 / (2 * 7) * 1.5 + 10;  sp = s_ego + v0 * ta + D;  tc = ta + D / (0.75 * v0);
            half = nl * lw / 2;  latS = half + 1.2;  latE = -(half + 1.2);  spd = 1.4;
            addPed(sc, info, sp, latS, latE, spd, max(0, tc - abs(latS - cen(egoLane)) / spd));  info.nped = 1;  roles{end+1} = 'pedestrian';
            desc{end+1} = sprintf('pedestrian crossing %.0f m ahead of the take-over point', D);
        case 'follower'
            addCar(sc, info, s_ego - 15, cen(egoLane), @(t) max(0, v0 - 5 * max(0, t - (ta + 1.8))), T);  info.follower = 1;  roles{end+1} = 'follower';
            desc{end+1} = 'follower 15 m behind, reacts after 1.8 s';
        case 'rightcar'
            if egoLane < nl
                addCar(sc, info, s_ego + 5, cen(min(egoLane + 1, nl)), @(t) v0 + 0 * t, T);  info.nadj = 1;  roles{end+1} = 'car on the right';
                desc{end+1} = 'car travelling alongside on the right';
            end
        case 'empty'
        otherwise
            error('Unknown content %s.', o.content);
    end
end

if isempty(desc), desc = {'empty road'}; end
info.desc = desc;  info.roles = roles;
info.title = sprintf('%s #%d: %d lanes%s, lane %d, %.0f m/s, R>=%.0f m', o.type, o.seed, nd, ternary(hasEdge, [' + ' lower(edgeType)], ''), egoLane, v0, Rmin);
end

%% ------------------------------------------------------------------ helpers
function [x, y, h] = posAt(info, s, lat)
h = interp1(info.sd, info.hd, s);
x = interp1(info.sd, info.xd, s) - lat .* sin(h);
y = interp1(info.sd, info.yd, s) + lat .* cos(h);
end

function addCar(sc, info, s0, lat, vfun, T)
tg = (0:0.05:T + 30)';  v = vfun(tg);
[x0, y0, h0] = posAt(info, s0, lat);
last = find(v > 0.3, 1, 'last');
if isempty(last) || last < 3
    vehicle(sc, 'ClassID', 1, 'Position', [x0 y0 0], 'Yaw', rad2deg(h0));  return
end
sT = s0 + cumtrapz(tg(1:last), v(1:last));
idx = find(info.s > s0 + 2 & info.s < sT(end));
if numel(idx) < 1
    vehicle(sc, 'ClassID', 1, 'Position', [x0 y0 0], 'Yaw', rad2deg(h0));  return
end
tw = interp1(sT, tg(1:last), info.s(idx));
[xs, ys] = posAt(info, info.s(idx), lat);
wp = [x0 y0 0; xs ys zeros(numel(idx), 1)];
sp = [vfun(0); max(0.3, vfun(tw))];
car = vehicle(sc, 'ClassID', 1, 'Position', wp(1, :));
trajectory(car, wp, sp);
end

function addPed(sc, info, s, latS, latE, spd, tstart)
[x0, y0] = posAt(info, s, latS);  [x1, y1] = posAt(info, s, latE);
try
    ped = actor(sc, 'ClassID', 4, 'Length', 0.24, 'Width', 0.45, 'Height', 1.7, 'Position', [x0 y0 0], 'RCSPattern', [-8 -8; -8 -8]);
catch
    ped = actor(sc, 'ClassID', 4, 'Length', 0.24, 'Width', 0.45, 'Height', 1.7, 'Position', [x0 y0 0]);
end
trajectory(ped, [x0 y0 0; x1 y1 0], spd, [tstart 0]);
end

function v = ternary(c, a, b)
if c, v = a; else, v = b; end
end
