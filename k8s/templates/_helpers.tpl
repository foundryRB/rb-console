{{/* Common labels applied to every resource in this chart. */}}
{{- define "foundry-console.labels" -}}
app.kubernetes.io/name: foundry-console
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: foundry-console
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version }}
{{- end -}}

{{/* Subset suitable for matchLabels / selector. */}}
{{- define "foundry-console.selectorLabels" -}}
app.kubernetes.io/name: foundry-console
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}
