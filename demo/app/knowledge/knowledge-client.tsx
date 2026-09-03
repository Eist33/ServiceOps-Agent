'use client';

// oxlint-disable next/no-html-link-for-pages -- Vinext Docker navigation requires full document requests.

import { useEffect, useMemo, useState } from 'react';
import {
  ArrowLeft,
  BookOpenCheck,
  ChartNoAxesCombined,
  CircleAlert,
  FileClock,
  Loader2,
  Plus,
  Search,
  ShieldCheck,
} from 'lucide-react';

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Badge } from '@/components/ui/badge';
import { Button, buttonVariants } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Field, FieldDescription, FieldGroup, FieldLabel } from '@/components/ui/field';
import { Input } from '@/components/ui/input';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Textarea } from '@/components/ui/textarea';
import {
  type KnowledgeArticleData,
  deactivateKnowledgeArticle,
  listKnowledgeArticles,
  publishKnowledgeArticle,
} from '@/lib/api';

const initialForm = {
  title: '平台退换货规则',
  version: '2026-09',
  section: '',
  keywords: '',
  content: '',
  source_uri: 'kb://after-sales/2026-09/',
};

export default function KnowledgeClient() {
  const [articles, setArticles] = useState<KnowledgeArticleData[]>([]);
  const [query, setQuery] = useState('');
  const [form, setForm] = useState(initialForm);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [articleToDeactivate, setArticleToDeactivate] =
    useState<KnowledgeArticleData | null>(null);

  async function loadArticles() {
    const data = await listKnowledgeArticles();
    setArticles(data);
  }

  useEffect(() => {
    let cancelled = false;
    async function initialize() {
      try {
        const data = await listKnowledgeArticles();
        if (!cancelled) setArticles(data);
      } catch (caught) {
        if (!cancelled) {
          setError(caught instanceof Error ? caught.message : '知识条款加载失败');
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void initialize();
    return () => {
      cancelled = true;
    };
  }, []);

  const filteredArticles = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    if (!normalized) return articles;
    return articles.filter((article) =>
      [
        article.title,
        article.version,
        article.section,
        article.content,
        article.keywords.join(' '),
      ]
        .join(' ')
        .toLowerCase()
        .includes(normalized),
    );
  }, [articles, query]);

  const activeCount = articles.filter((article) => article.active).length;
  const versionCount = new Set(articles.map((article) => article.version)).size;

  async function publish(event: { preventDefault(): void }) {
    event.preventDefault();
    if (saving) return;
    setSaving(true);
    setError('');
    setNotice('');
    try {
      const article = await publishKnowledgeArticle({
        title: form.title,
        version: form.version,
        section: form.section,
        content: form.content,
        keywords: form.keywords
          .split(/[,，\s]+/)
          .map((keyword) => keyword.trim())
          .filter(Boolean),
        source_uri: form.source_uri,
      });
      await loadArticles();
      setForm((current) => ({
        ...initialForm,
        version: current.version,
        source_uri: current.source_uri,
      }));
      setNotice(`${article.section} · ${article.version} 已发布，检索现已使用新版本。`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '发布失败');
    } finally {
      setSaving(false);
    }
  }

  async function deactivate() {
    if (!articleToDeactivate) return;
    const target = articleToDeactivate;
    setSaving(true);
    setError('');
    try {
      await deactivateKnowledgeArticle(target.id);
      await loadArticles();
      setNotice(`${target.section} · ${target.version} 已停用，不再参与客服检索。`);
      setArticleToDeactivate(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '停用失败');
    } finally {
      setSaving(false);
    }
  }

  return (
    <main className="min-h-screen bg-[#f5f8f9] text-foreground">
      <header className="border-b bg-white">
        <div className="mx-auto flex h-16 max-w-[1500px] items-center justify-between px-4 lg:px-8">
          <div className="flex items-center gap-3">
            <span className="grid size-9 place-items-center rounded-xl bg-primary text-primary-foreground">
              <BookOpenCheck className="size-4.5" />
            </span>
            <div>
              <p className="text-sm font-semibold">Harbor Knowledge</p>
              <p className="text-[11px] text-muted-foreground">售后知识运营台</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <a
              className={buttonVariants({ variant: 'outline', size: 'sm' })}
              href="/operations"
            >
              <ChartNoAxesCombined /> 运营看板
            </a>
            <a className={buttonVariants({ variant: 'outline', size: 'sm' })} href="/">
              <ArrowLeft /> 返回客服工作台
            </a>
          </div>
        </div>
      </header>

      <div className="mx-auto max-w-[1500px] space-y-6 px-4 py-7 lg:px-8">
        <section className="flex flex-col justify-between gap-4 lg:flex-row lg:items-end">
          <div>
            <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.14em] text-primary">
              <ShieldCheck className="size-4" /> 运营身份 · 许知夏
            </div>
            <h1 className="text-2xl font-semibold tracking-tight">知识条款与版本</h1>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">
              发布新条款版本后，同一条款的旧版本会自动退出检索；所有历史版本继续保留，便于审计和回溯。
            </p>
          </div>
          <div className="grid grid-cols-3 gap-2 sm:min-w-md">
            <Metric label="条款记录" value={articles.length} />
            <Metric label="当前生效" value={activeCount} />
            <Metric label="版本数量" value={versionCount} />
          </div>
        </section>

        {(error || notice) && (
          <div
            className={`flex items-start gap-2 rounded-xl border px-4 py-3 text-sm ${error ? 'border-red-100 bg-red-50 text-red-700' : 'border-emerald-100 bg-emerald-50 text-emerald-800'}`}
            role={error ? 'alert' : 'status'}
          >
            {error ? <CircleAlert className="mt-0.5 size-4" /> : <BookOpenCheck className="mt-0.5 size-4" />}
            {error || notice}
          </div>
        )}

        <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_390px]">
          <Card>
            <CardHeader className="border-b">
              <CardTitle>知识版本库</CardTitle>
              <CardDescription>生效状态直接决定客服 Agent 的检索范围。</CardDescription>
              <div className="relative mt-3 max-w-sm">
                <Search className="absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  aria-label="搜索知识条款"
                  className="pl-8"
                  placeholder="搜索条款、版本或关键词"
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                />
              </div>
            </CardHeader>
            <CardContent className="px-0">
              {loading ? (
                <div className="flex justify-center py-16 text-sm text-muted-foreground">
                  <Loader2 className="mr-2 size-4 animate-spin" /> 正在加载知识版本…
                </div>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="pl-4">条款</TableHead>
                      <TableHead>版本</TableHead>
                      <TableHead>内容摘要</TableHead>
                      <TableHead>状态</TableHead>
                      <TableHead className="pr-4 text-right">操作</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {filteredArticles.map((article) => (
                      <TableRow key={article.id}>
                        <TableCell className="pl-4 font-medium">{article.section}</TableCell>
                        <TableCell>{article.version}</TableCell>
                        <TableCell className="max-w-md whitespace-normal text-xs leading-5 text-muted-foreground">
                          {article.content}
                        </TableCell>
                        <TableCell>
                          <Badge
                            className={
                              article.active
                                ? 'bg-emerald-50 text-emerald-700'
                                : 'bg-slate-100 text-slate-600'
                            }
                            variant="secondary"
                          >
                            {article.active ? '生效中' : '历史版本'}
                          </Badge>
                        </TableCell>
                        <TableCell className="pr-4 text-right">
                          {article.active ? (
                            <Button
                              size="xs"
                              variant="ghost"
                              onClick={() => setArticleToDeactivate(article)}
                            >
                              停用
                            </Button>
                          ) : (
                            <span className="text-xs text-muted-foreground">已归档</span>
                          )}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>

          <Card className="h-fit xl:sticky xl:top-6">
            <CardHeader className="border-b">
              <div className="mb-2 grid size-9 place-items-center rounded-xl bg-sky-50 text-sky-700">
                <Plus className="size-4" />
              </div>
              <CardTitle>发布新版本</CardTitle>
              <CardDescription>相同标题和条款号的当前版本会自动归档。</CardDescription>
            </CardHeader>
            <CardContent>
              <form onSubmit={publish}>
                <FieldGroup>
                  <Field>
                    <FieldLabel htmlFor="knowledge-title">知识文档</FieldLabel>
                    <Input
                      id="knowledge-title"
                      required
                      value={form.title}
                      onChange={(event) => setForm({ ...form, title: event.target.value })}
                    />
                  </Field>
                  <div className="grid grid-cols-2 gap-3">
                    <Field>
                      <FieldLabel htmlFor="knowledge-version">版本</FieldLabel>
                      <Input
                        id="knowledge-version"
                        required
                        placeholder="2026-09"
                        value={form.version}
                        onChange={(event) => setForm({ ...form, version: event.target.value })}
                      />
                    </Field>
                    <Field>
                      <FieldLabel htmlFor="knowledge-section">条款号</FieldLabel>
                      <Input
                        id="knowledge-section"
                        required
                        placeholder="第 2.1 条"
                        value={form.section}
                        onChange={(event) => setForm({ ...form, section: event.target.value })}
                      />
                    </Field>
                  </div>
                  <Field>
                    <FieldLabel htmlFor="knowledge-keywords">关键词</FieldLabel>
                    <Input
                      id="knowledge-keywords"
                      required
                      placeholder="退货，无理由，10天"
                      value={form.keywords}
                      onChange={(event) => setForm({ ...form, keywords: event.target.value })}
                    />
                    <FieldDescription>使用逗号或空格分隔，帮助口语化检索命中。</FieldDescription>
                  </Field>
                  <Field>
                    <FieldLabel htmlFor="knowledge-content">条款内容</FieldLabel>
                    <Textarea
                      id="knowledge-content"
                      className="min-h-28 resize-y"
                      required
                      placeholder="填写对客服回答生效的完整条款内容"
                      value={form.content}
                      onChange={(event) => setForm({ ...form, content: event.target.value })}
                    />
                  </Field>
                  <Field>
                    <FieldLabel htmlFor="knowledge-source">来源地址</FieldLabel>
                    <Input
                      id="knowledge-source"
                      required
                      value={form.source_uri}
                      onChange={(event) => setForm({ ...form, source_uri: event.target.value })}
                    />
                  </Field>
                  <Button className="w-full" disabled={saving} type="submit">
                    {saving ? <Loader2 className="animate-spin" /> : <FileClock />}
                    发布并立即生效
                  </Button>
                </FieldGroup>
              </form>
            </CardContent>
          </Card>
        </div>
      </div>

      <AlertDialog
        open={Boolean(articleToDeactivate)}
        onOpenChange={(open) => !open && setArticleToDeactivate(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>停用当前知识条款？</AlertDialogTitle>
            <AlertDialogDescription>
              {articleToDeactivate?.section} · {articleToDeactivate?.version} 停用后将立即退出客服检索，但历史记录仍会保留。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={saving}>继续保留</AlertDialogCancel>
            <AlertDialogAction disabled={saving} variant="destructive" onClick={() => void deactivate()}>
              {saving ? '正在停用…' : '确认停用'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </main>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-xl border bg-white px-3 py-2.5">
      <p className="text-[10px] text-muted-foreground">{label}</p>
      <p className="mt-1 text-lg font-semibold">{value}</p>
    </div>
  );
}
