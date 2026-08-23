import { createClient } from "npm:@supabase/supabase-js@2.45.4";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Client-Info, Apikey",
};

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") {
    return new Response(null, { status: 200, headers: corsHeaders });
  }

  try {
    const url = new URL(req.url);
    const repo = url.searchParams.get("repo");
    const issueNumber = url.searchParams.get("issue_number");

    if (!repo || !issueNumber) {
      return new Response(
        JSON.stringify({ error: "Both repo and issue_number are required" }),
        { status: 400, headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    const ghToken = Deno.env.get("GITHUB_TOKEN") || Deno.env.get("GH_TOKEN");

    const headers: Record<string, string> = {
      "Accept": "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
    };
    if (ghToken) {
      headers["Authorization"] = `Bearer ${ghToken}`;
    }

    const ghUrl = `https://api.github.com/repos/${repo}/issues/${issueNumber}`;
    const ghRes = await fetch(ghUrl, { headers });

    if (!ghRes.ok) {
      const errBody = await ghRes.text();
      return new Response(
        JSON.stringify({ error: `GitHub API returned ${ghRes.status}`, detail: errBody }),
        { status: ghRes.status, headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    const issue = await ghRes.json();

    return new Response(
      JSON.stringify({
        title: issue.title || "",
        body: issue.body || "",
        number: issue.number,
        state: issue.state,
        labels: (issue.labels || []).map((l: any) => l.name),
        user: issue.user?.login || "",
        html_url: issue.html_url || "",
        created_at: issue.created_at || "",
      }),
      { status: 200, headers: { ...corsHeaders, "Content-Type": "application/json" } }
    );
  } catch (err) {
    return new Response(
      JSON.stringify({ error: err.message || "Internal server error" }),
      { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } }
    );
  }
});
