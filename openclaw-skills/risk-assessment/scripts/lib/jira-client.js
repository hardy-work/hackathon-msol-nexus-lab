'use strict';

const https = require('https');

function request(method, urlStr, email, token, jsonBody) {
  return new Promise((resolve, reject) => {
    const url = new URL(urlStr);
    const auth = Buffer.from(`${email}:${token}`).toString('base64');
    const body = jsonBody !== undefined ? JSON.stringify(jsonBody) : undefined;
    const req = https.request(
      {
        hostname: url.hostname,
        path: url.pathname + url.search,
        method,
        headers: {
          Authorization: `Basic ${auth}`,
          Accept: 'application/json',
          ...(body ? { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(body) } : {}),
        },
      },
      (res) => {
        let data = '';
        res.on('data', (c) => (data += c));
        res.on('end', () => resolve({ status: res.statusCode, body: data }));
      }
    );
    req.on('error', reject);
    if (body) req.write(body);
    req.end();
  });
}

const FIELDS = 'summary,assignee,status,duedate,timeoriginalestimate,timespent,updated,customfield_10020';

async function searchIssues({ baseUrl, email, token, projectKey }) {
  const jql = encodeURIComponent(`project=${projectKey} AND sprint in openSprints()`);
  const url = `${baseUrl}/rest/api/3/search?jql=${jql}&fields=${FIELDS}&maxResults=200`;
  const res = await request('GET', url, email, token);
  if (res.status !== 200) throw new Error(`Jira search error (${res.status}): ${res.body}`);
  return JSON.parse(res.body).issues || [];
}

async function createIssue({ baseUrl, email, token, projectKey, issueType, summary, description }) {
  const url = `${baseUrl}/rest/api/3/issue`;
  const payload = {
    fields: {
      project: { key: projectKey },
      issuetype: { name: issueType },
      summary,
      description: {
        type: 'doc',
        version: 1,
        content: [{ type: 'paragraph', content: [{ type: 'text', text: description }] }],
      },
    },
  };
  const res = await request('POST', url, email, token, payload);
  if (res.status !== 201) throw new Error(`Jira create issue error (${res.status}): ${res.body}`);
  return JSON.parse(res.body);
}

async function updateIssue({ baseUrl, email, token, issueKey, fields }) {
  const url = `${baseUrl}/rest/api/3/issue/${issueKey}`;
  const res = await request('PUT', url, email, token, { fields });
  if (res.status !== 204) throw new Error(`Jira update issue error (${res.status}): ${res.body}`);
}

module.exports = { searchIssues, createIssue, updateIssue };
