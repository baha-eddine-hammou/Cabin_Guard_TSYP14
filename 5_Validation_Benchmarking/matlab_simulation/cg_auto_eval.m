function E = cg_auto_eval(mk, o, t, X, Y, psi, vx, info)
% CG_AUTO_EVAL  Judges a finished run against the TRUE motion of every other actor (cars, pedestrians), offline.
%   The scenario is created again and stepped on its own (its actors follow scripted paths, independent of the ego).
%   Collision = the ego body rectangle overlaps an actor's rectangle at any instant of the log (0.02 s steps).
%   Both reference points are taken as the rear-axle centre (the convention of the scenario / sensors).
[sc2, ~] = mk();
try, sc2.StopTime = o.T; catch, end
nA = numel(sc2.Actors);
ids = [sc2.Actors.ActorID];
Lg = zeros(1, nA);  Wd = zeros(1, nA);  RO = zeros(1, nA);  Cl = zeros(1, nA);
for a = 1:nA
    ac = sc2.Actors(a);  Lg(a) = ac.Length;  Wd(a) = ac.Width;  Cl(a) = ac.ClassID;
    try, RO(a) = ac.RearOverhang; catch, RO(a) = 0; end
end
tt = [];  P = zeros(0, nA, 2);  Yw = zeros(0, nA);  k = 0;
while true
    k = k + 1;  tt(k, 1) = sc2.SimulationTime; %#ok<AGROW>
    for a = 1:nA
        ac = sc2.Actors(a);  P(k, a, :) = ac.Position(1:2);  Yw(k, a) = ac.Yaw;
    end
    if ~advance(sc2) || tt(k) > o.T + 0.5, break, end
end
ego = find(ids == info.egoID);
others = setdiff(1:nA, ego);
tq = min(max(t, tt(1)), tt(end));                 % hold the last pose if the scenario ended early
Pi = zeros(numel(t), nA, 2);  Yi = zeros(numel(t), nA);
for a = others
    Pi(:, a, 1) = interp1(tt, P(:, a, 1), tq, 'linear');
    Pi(:, a, 2) = interp1(tt, P(:, a, 2), tq, 'linear');
    Yi(:, a) = interp1(tt, unwrap(deg2rad(Yw(:, a))), tq, 'linear');
end
vxe = gradient(X, t);  vye = gradient(Y, t);
E = struct('pre_takeover', false, 'hit_role', '', 'hit_rel', [NaN NaN], 'collision', false, 'n_collisions', 0, 'first_t', NaN, 'hit_class', NaN, 'hit_id', NaN, 'impact', 0, 'min_dist', inf, 'min_dist_ped', inf, 'min_gap', inf, 'min_gap_ped', inf);
hitDone = false(1, nA);
for a = others
    d = hypot(Pi(:, a, 1) - X, Pi(:, a, 2) - Y);
    E.min_dist = min(E.min_dist, min(d));
    if Cl(a) == 4, E.min_dist_ped = min(E.min_dist_ped, min(d)); end
    for j = find(d < 20)'                                         % clearance between the car bodies (rectangles), not between the centres
        g = quadgap(rect(X(j), Y(j), psi(j), 4.7, 1.8, 1.0), rect(Pi(j, a, 1), Pi(j, a, 2), Yi(j, a), max(Lg(a), 0.3), max(Wd(a), 0.3), RO(a)));
        E.min_gap = min(E.min_gap, g);
        if Cl(a) == 4, E.min_gap_ped = min(E.min_gap_ped, g); end
    end
    cand = find(d < 9);
    for j = cand'
        c1 = rect(X(j), Y(j), psi(j), 4.7, 1.8, 1.0);
        c2 = rect(Pi(j, a, 1), Pi(j, a, 2), Yi(j, a), max(Lg(a), 0.3), max(Wd(a), 0.3), RO(a));
        if sat(c1, c2) && t(j) < o.t_act
            E.pre_takeover = true;  E.pre_t = t(j);  if isfield(info, 'roles') && a <= numel(info.roles), E.pre_role = info.roles{a}; else, E.pre_role = sprintf('actor %d', ids(a)); end
            break                       % contact BEFORE the driver stopped responding: the scene is invalid, not a failure of the system
        end
        if sat(c1, c2)
            if ~hitDone(a)
                hitDone(a) = true;  E.n_collisions = E.n_collisions + 1;
                vaX = gradient(Pi(:, a, 1), t);  vaY = gradient(Pi(:, a, 2), t);
                imp = hypot(vxe(j) - vaX(j), vye(j) - vaY(j));
                if ~E.collision || t(j) < E.first_t
                    E.first_t = t(j);  E.hit_class = Cl(a);  E.hit_id = ids(a);  E.impact = imp;
                    if isfield(info, 'roles') && a <= numel(info.roles), E.hit_role = info.roles{a}; else, E.hit_role = sprintf('actor %d', ids(a)); end
                    dxy = [Pi(j, a, 1) - X(j), Pi(j, a, 2) - Y(j)];
                    E.hit_rel = [cos(psi(j)) * dxy(1) + sin(psi(j)) * dxy(2), -sin(psi(j)) * dxy(1) + cos(psi(j)) * dxy(2)];   % ego frame: x ahead, y left
                end
                E.collision = true;
            end
            break
        end
    end
end
% stopping
ia = find(t >= o.t_act, 1);
istop = find(vx < 0.1 & t > o.t_act, 1);
sx = [0; cumsum(hypot(diff(X), diff(Y)))];
if isempty(istop) || isempty(ia), E.tstop = NaN;  E.stopdist = NaN; else, E.tstop = t(istop) - o.t_act;  E.stopdist = sx(istop) - sx(ia); end
E.v_end = vx(end);
acc = gradient(movmean(vx, 25), t);
E.decel_max = -min(acc);
% where did it end up (generated scenes: lane / shoulder / off road)
E.lane = '';  E.lat_end = NaN;  E.lat_start = NaN;
if isfield(info, 'sd')
    [~, j] = min((info.xd - X(end)).^2 + (info.yd - Y(end)).^2);
    E.lat_end = cos(info.hd(j)) * (Y(end) - info.yd(j)) - sin(info.hd(j)) * (X(end) - info.xd(j));
    [~, j0] = min((info.xd - X(1)).^2 + (info.yd - Y(1)).^2);
    E.lat_start = cos(info.hd(j0)) * (Y(1) - info.yd(j0)) - sin(info.hd(j0)) * (X(1) - info.xd(j0));
    [dm, kk] = min(abs(E.lat_end - info.cen));
    half = info.nl * info.lw / 2;
    if abs(E.lat_end) > half - 0.2, E.lane = 'OFF ROAD';
    elseif kk <= info.nd, E.lane = sprintf('lane %d', kk);
    elseif strcmp(info.type, 'city'), E.lane = 'parking lane';
    else, E.lane = 'shoulder'; end
    E.in_traffic_lane = kk <= info.nd && dm < info.lw / 2;
end
% tracks of the other actors on a 0.1 s grid (for plots and the video)
g = 1:5:numel(t);
E.tracks = struct('id', num2cell(ids(others)), 'cls', num2cell(Cl(others)), 'L', num2cell(Lg(others)), 'W', num2cell(Wd(others)), 'RO', num2cell(RO(others)), ...
                  'x', [], 'y', [], 'yaw', []);
for q = 1:numel(others)
    a = others(q);  E.tracks(q).x = Pi(g, a, 1);  E.tracks(q).y = Pi(g, a, 2);  E.tracks(q).yaw = Yi(g, a);
end
E.tgrid = t(g);
end

function c = rect(x, y, yaw, L, W, RO)
loc = [-RO -W/2; L - RO -W/2; L - RO W/2; -RO W/2];
R = [cos(yaw) -sin(yaw); sin(yaw) cos(yaw)];
c = (R * loc')' + [x y];
end

function hit = sat(A, B)
% separating-axis test for two convex quadrilaterals
hit = true;
for P = {A, B}
    Q = P{1};
    for i = 1:4
        e = Q(mod(i, 4) + 1, :) - Q(i, :);  nrm = [-e(2) e(1)];
        pa = A * nrm';  pb = B * nrm';
        if max(pa) < min(pb) || max(pb) < min(pa), hit = false;  return, end
    end
end
end

function g = quadgap(A, B)
% distance between two convex quadrilaterals (0 if they touch or overlap)
if sat(A, B), g = 0;  return, end
g = inf;
for k = 1:2
    if k == 1, P = A; Q = B; else, P = B; Q = A; end
    for i = 1:4
        p = P(i, :);
        for m = 1:4
            a = Q(m, :);  b = Q(mod(m, 4) + 1, :);
            ab = b - a;  u = max(0, min(1, dot(p - a, ab) / dot(ab, ab)));
            g = min(g, norm(p - (a + u * ab)));
        end
    end
end
end
