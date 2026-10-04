"""Treina tres classificadores e grava o de maior F1."""
from __future__ import annotations

import json
from pathlib import Path

import joblib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, f1_score
from sklearn.model_selection import cross_val_score, train_test_split
from sklearn.preprocessing import StandardScaler
from sqlalchemy import create_engine, text

from src.features import FEATURES

URL = "postgresql+psycopg2://postgres:postgres@127.0.0.1:5434/varejo_amazonia"
ROOT = Path(__file__).resolve().parents[1]
NUMERICAS = [
    "dias_desde_cadastro", "mes_ultima_compra", "total_compras", "qtd_compras",
    "ticket_medio", "produtos_distintos", "idade", "desvio_valor", "recencia_dias",
    "freq_mensal", "compras_90d",
]


def treinar() -> dict:
    engine = create_engine(URL)
    dados = pd.read_sql(text("SELECT * FROM gold.cliente_features"), engine)
    X = dados[FEATURES]
    y = dados["churn"]
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    scaler = StandardScaler()
    X_train = X_train.copy()
    X_test = X_test.copy()
    X_train[NUMERICAS] = scaler.fit_transform(X_train[NUMERICAS])
    X_test[NUMERICAS] = scaler.transform(X_test[NUMERICAS])
    (ROOT / "data").mkdir(parents=True, exist_ok=True)
    X_train.to_csv(ROOT / "data" / "X_train.csv", index=False)
    X_test.to_csv(ROOT / "data" / "X_test.csv", index=False)
    y_train.to_csv(ROOT / "data" / "y_train.csv", index=False)
    y_test.to_csv(ROOT / "data" / "y_test.csv", index=False)

    base_classe = int(y_train.mode().iloc[0])
    base_pred = [base_classe] * len(y_test)
    modelos = {
        "Logistic Regression": LogisticRegression(max_iter=1000),
        "Random Forest": RandomForestClassifier(n_estimators=200, random_state=42),
        "Gradient Boosting": GradientBoostingClassifier(n_estimators=150, random_state=42),
    }
    linhas = []
    relatorios = [
        "Baseline (classe majoritaria do treino)\n"
        f"accuracy={accuracy_score(y_test, base_pred):.3f} f1={f1_score(y_test, base_pred):.3f}"
    ]
    ajustados = {}
    for nome, modelo in modelos.items():
        cv = cross_val_score(modelo, X_train, y_train, cv=5, scoring="f1")
        modelo.fit(X_train, y_train)
        previsto = modelo.predict(X_test)
        item = {
            "modelo": nome,
            "accuracy": round(float(accuracy_score(y_test, previsto)), 4),
            "f1": round(float(f1_score(y_test, previsto)), 4),
            "cv_f1_mean": round(float(cv.mean()), 4),
        }
        linhas.append(item)
        ajustados[nome] = modelo
        relatorios.append(f"{nome}\n{classification_report(y_test, previsto, digits=3)}")

    ranking = pd.DataFrame(linhas).sort_values("f1", ascending=False)
    melhor_nome = ranking.iloc[0]["modelo"]
    pacote = {
        "modelo": ajustados[melhor_nome],
        "nome": melhor_nome,
        "scaler": scaler,
        "colunas": FEATURES,
        "colunas_numericas": NUMERICAS,
        "metricas": linhas,
        "baseline_accuracy": round(float(accuracy_score(y_test, base_pred)), 4),
        "baseline_f1": round(float(f1_score(y_test, base_pred)), 4),
    }
    (ROOT / "modelos").mkdir(parents=True, exist_ok=True)
    joblib.dump(pacote, ROOT / "modelos" / "modelo_churn.pkl")
    (ROOT / "saidas").mkdir(parents=True, exist_ok=True)
    (ROOT / "saidas" / "p15_relatorios.txt").write_text("\n\n".join(relatorios), encoding="utf-8")
    resultado = {
        "clientes": int(len(dados)),
        "churn_rate": round(float(y.mean()), 4),
        "treino": int(len(X_train)),
        "teste": int(len(X_test)),
        "baseline_accuracy": pacote["baseline_accuracy"],
        "baseline_f1": pacote["baseline_f1"],
        "modelos": linhas,
        "melhor": melhor_nome,
    }
    (ROOT / "saidas" / "modelo.json").write_text(json.dumps(resultado, indent=2, ensure_ascii=False), encoding="utf-8")

    evid = ROOT / "evidencias"
    evid.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(7, 4))
    sns.barplot(data=ranking, x="modelo", y="f1", ax=ax, color="#0f766e")
    ax.set_ylim(0, 1)
    ax.set_title("F1 no teste")
    fig.tight_layout()
    fig.savefig(evid / "modelos_f1.png", dpi=120)
    plt.close(fig)
    return resultado


if __name__ == "__main__":
    print(treinar())
