"use client";

import { useState, useEffect, useCallback } from "react";
import {
  fetchPatterns,
  type PatternData,
} from "@/lib/api";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Search, RefreshCw, AlertCircle, Star, Hash } from "lucide-react";

export default function PatternsPage() {
  const [patterns, setPatterns] = useState<PatternData[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [categoryFilter, setCategoryFilter] = useState("");
  const [searchQuery, setSearchQuery] = useState("");

  const loadPatterns = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await fetchPatterns(
        categoryFilter || undefined,
      );
      setPatterns(result.items);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to load patterns",
      );
    } finally {
      setLoading(false);
    }
  }, [categoryFilter]);

  useEffect(() => {
    loadPatterns();
  }, [loadPatterns]);

  const filteredPatterns = searchQuery
    ? patterns.filter(
        (p) =>
          p.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
          p.description.toLowerCase().includes(searchQuery.toLowerCase()),
      )
    : patterns;

  const categories = [...new Set(patterns.map((p) => p.category))];

  if (loading) {
    return (
      <div className="p-6 space-y-4">
        <h1 className="text-2xl font-bold">Process Patterns</h1>
        <div className="flex items-center gap-2 text-muted-foreground">
          <RefreshCw className="h-4 w-4 animate-spin" />
          Loading patterns...
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Process Patterns</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Discover reusable process patterns across engagements
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={loadPatterns}>
          <RefreshCw className="h-3 w-3 mr-1.5" />
          Refresh
        </Button>
      </div>

      {error && (
        <Card className="border-destructive/50 bg-destructive/5">
          <CardContent className="pt-6">
            <div className="flex items-start gap-3">
              <AlertCircle className="h-5 w-5 text-destructive mt-0.5" />
              <p className="text-sm text-destructive">{error}</p>
            </div>
          </CardContent>
        </Card>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Total Patterns</CardDescription>
            <CardTitle className="text-3xl">{patterns.length}</CardTitle>
          </CardHeader>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Categories</CardDescription>
            <CardTitle className="text-3xl">{categories.length}</CardTitle>
          </CardHeader>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Avg Effectiveness</CardDescription>
            <CardTitle className="text-3xl">
              {patterns.length > 0
                ? (
                    patterns.reduce((s, p) => s + p.effectiveness_score, 0) /
                    patterns.length
                  ).toFixed(1)
                : "—"}
            </CardTitle>
          </CardHeader>
        </Card>
      </div>

      <div className="flex gap-3">
        <div className="relative flex-1 max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search patterns..."
            className="pl-9"
          />
        </div>
        <div className="flex gap-1.5 flex-wrap">
          <Button
            size="sm"
            variant={categoryFilter === "" ? "default" : "outline"}
            onClick={() => setCategoryFilter("")}
          >
            All
          </Button>
          {categories.map((cat) => (
            <Button
              key={cat}
              size="sm"
              variant={categoryFilter === cat ? "default" : "outline"}
              onClick={() => setCategoryFilter(cat)}
            >
              {cat}
            </Button>
          ))}
        </div>
      </div>

      {filteredPatterns.length === 0 ? (
        <Card>
          <CardContent className="pt-6">
            <p className="text-sm text-muted-foreground text-center py-8">
              No patterns found. Patterns are discovered automatically as
              engagements complete.
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filteredPatterns.map((pattern) => (
            <Card key={pattern.id}>
              <CardHeader>
                <div className="flex items-start justify-between">
                  <CardTitle className="text-base">{pattern.title}</CardTitle>
                  <Badge variant="outline">{pattern.category}</Badge>
                </div>
                <CardDescription className="line-clamp-2">
                  {pattern.description}
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="flex items-center justify-between text-sm">
                  <span className="flex items-center gap-1 text-muted-foreground">
                    <Star className="h-3.5 w-3.5" />
                    {pattern.effectiveness_score.toFixed(1)}
                  </span>
                  <span className="flex items-center gap-1 text-muted-foreground">
                    <Hash className="h-3.5 w-3.5" />
                    Used {pattern.usage_count}x
                  </span>
                  {pattern.industry && (
                    <Badge variant="secondary" className="text-xs">
                      {pattern.industry}
                    </Badge>
                  )}
                </div>
                {pattern.tags && pattern.tags.length > 0 && (
                  <div className="flex gap-1 mt-3 flex-wrap">
                    {pattern.tags.map((tag) => (
                      <Badge key={tag} variant="outline" className="text-xs">
                        {tag}
                      </Badge>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
