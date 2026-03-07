

## Painel Dashboard - Gateway de Pagamentos

### 1. Layout Principal
- Sidebar com navegação: Dashboard, Links/Checkouts, Retentativas, Configurações, Relatórios
- Header com nome do usuário e notificações
- Design escuro e profissional

### 2. Dashboard (Home)
- Cards de métricas: total de vendas, taxa de conversão, transações aprovadas/recusadas, receita do dia
- Gráfico de vendas dos últimos 7/30 dias (Recharts)
- Últimas transações em tabela

### 3. Links / Checkouts
- Lista de links de checkout criados
- Criar/editar link: nome do produto, valor, descrição, URL da API de pagamento
- Pré-visualização antes de disparar
- Copiar link gerado
- Status do link (ativo/inativo)

### 4. Configurações de API
- Formulário para configurar URL base da API
- Headers customizáveis (chave/valor)
- Token de autenticação
- Botão de testar conexão
- Salvar múltiplas configurações de API

### 5. Retentativas
- Painel de transações com falha
- Configurar regras de retentativa (quantidade, intervalo)
- Disparar retentativa manual
- Log de tentativas por transação

### 6. Relatórios / Análises
- Filtros por período, status, valor
- Gráficos de aprovação vs recusa
- Exportar dados (simulado)
- Tabela detalhada com busca

> **Nota:** Os dados serão mockados localmente (sem backend). As configurações de API ficam salvas no localStorage. Quando você conectar sua API real, basta trocar os endpoints.

