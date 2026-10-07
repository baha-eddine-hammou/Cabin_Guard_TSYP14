# IEEEtran LaTeX Templates & Code Snippets

This reference provides production-tested LaTeX snippets formatted specifically for IEEE conference templates (`IEEEtran.cls`).

---

## 1. High-Density Academic Tables (`booktabs`)

```latex
\begin{table}[htbp]
\caption{Comparative Matrix of Sensing Modalities Across Evaluated Etiology Classes}
\label{tab:modality_comparison}
\centering
\begin{tabular}{lccc}
\toprule
\textbf{Metric / Modality} & \textbf{Normal Driving} & \textbf{Cardiac Syncope} & \textbf{Epileptic Seizure} \\
\midrule
Eye Aspect Ratio ($EAR$)      & $0.28 \pm 0.04$      & $< 0.15$ ($> 2.0$\,s)    & Flutter / Deviation \\
Head Pitch Angle ($\theta_p$) & $-5^\circ \pm 3^\circ$& $< -25^\circ$ (Slump)    & Rhythmic Oscillations \\
Headrest IMU ($SER_{2-6\text{Hz}}$)& $< 0.18$         & $< 0.12$ (Atonic)        & $\mathbf{> 0.65}$ (Resonance) \\
Optical Heart Rate ($HR_{rPPG}$)& $72 \pm 8$\,BPM     & $<40$ or $>150$\,BPM     & $115 \pm 12$\,BPM \\
Seatback Pressure ($PSI$)      & $0.10 \pm 0.03$      & $\mathbf{> 0.75}$ (Loss) & $0.35 \pm 0.10$ \\
Steering Grip State           & Closed (Active)       & Disengaged ($> 2.0$\,s)  & Clenched / Erratic \\
\bottomrule
\end{tabular}
\end{table}
```

---

## 2. Multi-Line Mathematical Formulations

```latex
\begin{equation}
\label{eq:pos_rppg}
\begin{aligned}
S(t) &= P \cdot C_n(t) \\
     &= \begin{bmatrix} 0 & 1 & -1 \\ -2 & 1 & 1 \end{bmatrix} 
        \begin{bmatrix} 
        R(t)/\mu_R - 1 \\ 
        G(t)/\mu_G - 1 \\ 
        B(t)/\mu_B - 1 
        \end{bmatrix}
\end{aligned}
\end{equation}

\begin{equation}
\label{eq:ser_energy}
SER_{2-6\text{Hz}} = \frac{\displaystyle\int_{2.0}^{6.0} P_{aa}(f) \, df}{\displaystyle\int_{0.5}^{20.0} P_{aa}(f) \, df}
\end{equation}
```

---

## 3. Algorithm Block (`algorithmic`)

```latex
\begin{algorithm}[htbp]
\caption{Cross-Sensor Plausibility & Medical Verification Watchdog}
\label{alg:watchdog}
\begin{algorithmic}[1]
\REQUIRE Feature vector $\mathbf{x}(t)$, Confidence threshold $\Gamma = 0.85$, Window $T_{ver} = 2.0$\,s
\ENSURE Verified State $S_{final}$, Actuation Flag $F_{act}$
\STATE Compute Bayesian posteriors: $P(C_k \mid \mathbf{x}(t))$ for $k \in \{0, 1, 2\}$
\IF{$SNR_{camera} < -15$\,dB \OR FaceCount $== 0$}
    \STATE Set SystemState $\leftarrow$ \textsc{DegradedMode1} (Bypass Vision)
    \STATE Re-evaluate posteriors using $\mathbf{x}_{degraded} = [SER, PSI, Grip]^T$
\ENDIF
\IF{$P(C_1 \mid \mathbf{x}) \ge \Gamma$ \AND $SER_{2-6\text{Hz}} > 0.50$}
    \STATE Log Conflict: Syncope flagged with high motion $\to$ Suppress Trigger
    \RETURN $S_{final} \leftarrow \textsc{AnomalyLogged}, F_{act} \leftarrow \text{FALSE}$
\ENDIF
\IF{Class $C_k$ persists for duration $\ge T_{ver}$}
    \RETURN $S_{final} \leftarrow C_k, F_{act} \leftarrow \text{TRUE}$
\ELSE
    \RETURN $S_{final} \leftarrow \textsc{Evaluating}, F_{act} \leftarrow \text{FALSE}$
\ENDIF
\end{algorithmic}
\end{algorithm}
```

---

## 4. Full-Width Two-Column Figures

```latex
\begin{figure*}[t]
\centering
\includegraphics[width=0.98\textwidth]{figures/system_architecture_overview.pdf}
\caption{End-to-end operational pipeline of CabinGuard-ADI, delineating the multi-modal sensing layer, edge feature extraction, multi-etiology inference engine, UNECE R157 MRM execution, and secure V2X telematics broadcast.}
\label{fig:full_architecture}
\end{figure*}
```

