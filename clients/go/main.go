// Command registry is a read-only Go client for the project-registry database.
//
// It is the Go half of the README's "two clients, one Python and one Go": it
// opens the same local SQLite file the scanner writes and reads it through the
// same shared SQL views (v_projects / v_git_projects) that the Python Registry
// facade uses — no client-specific SQL, no writes. Populating the registry is
// the scanner's job (`uv run main.py`); this command only ever queries.
//
// Usage:
//
//	registry              # list all watched dirs (v_projects)
//	registry -git         # only git checkouts (v_git_projects)
//	registry -json        # emit JSON instead of a table
//	registry -db PATH     # read a specific database file
package main

import (
	"database/sql"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"text/tabwriter"

	_ "modernc.org/sqlite"
)

// defaultDBPath mirrors app/config_service/cnfg.py: ~/.config/dev-reg/registry.db.
func defaultDBPath() string {
	home, err := os.UserHomeDir()
	if err != nil {
		return "registry.db"
	}
	return filepath.Join(home, ".config", "dev-reg", "registry.db")
}

// project is one row of a v_* view. Only the fields a client displays are
// selected; the views expose the full record, so this can grow without SQL
// changes. tags arrives as JSON text (e.g. `["a","b"]`) and is decoded lazily.
type project struct {
	Name     string   `json:"project_name"`
	DirType  string   `json:"dir_type"`
	Branch   string   `json:"branch_name"`
	Cycle    string   `json:"cycle"`
	Tags     []string `json:"tags"`
	Notes    string   `json:"notes"`
	Path     string   `json:"path"`
}

func main() {
	dbPath := flag.String("db", defaultDBPath(), "path to the registry SQLite database")
	gitOnly := flag.Bool("git", false, "only git checkouts (reads v_git_projects)")
	asJSON := flag.Bool("json", false, "emit JSON instead of a table")
	flag.Parse()

	if err := run(*dbPath, *gitOnly, *asJSON, os.Stdout); err != nil {
		fmt.Fprintln(os.Stderr, "registry:", err)
		os.Exit(1)
	}
}

func run(dbPath string, gitOnly, asJSON bool, out *os.File) error {
	// A missing file is the common "haven't scanned yet" case; report it clearly
	// rather than letting the driver create an empty database in read-only mode.
	if _, err := os.Stat(dbPath); errors.Is(err, os.ErrNotExist) {
		return fmt.Errorf("no registry at %s — run the scanner first (uv run main.py)", dbPath)
	}

	// mode=ro: this client never writes, and must never create the file.
	db, err := sql.Open("sqlite", fmt.Sprintf("file:%s?mode=ro", dbPath))
	if err != nil {
		return err
	}
	defer db.Close()

	view := "v_projects"
	if gitOnly {
		view = "v_git_projects"
	}
	projects, err := queryProjects(db, view)
	if err != nil {
		return err
	}

	if asJSON {
		return writeJSON(out, projects)
	}
	return writeTable(out, projects, view)
}

func queryProjects(db *sql.DB, view string) ([]project, error) {
	// view is an in-code constant (v_projects / v_git_projects), never user input.
	rows, err := db.Query("SELECT project_name, dir_type, branch_name, cycle, tags, notes, path FROM " + view)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var projects []project
	for rows.Next() {
		var (
			name, dirType, branch, cycle, tags, notes, path sql.NullString
		)
		if err := rows.Scan(&name, &dirType, &branch, &cycle, &tags, &notes, &path); err != nil {
			return nil, err
		}
		projects = append(projects, project{
			Name:    name.String,
			DirType: dirType.String,
			Branch:  branch.String,
			Cycle:   cycle.String,
			Tags:    decodeTags(tags),
			Notes:   notes.String,
			Path:    path.String,
		})
	}
	return projects, rows.Err()
}

// decodeTags turns the JSON-encoded tags column into a slice. A NULL or
// unparseable value yields nil rather than an error — a bad tags blob should not
// break a listing.
func decodeTags(tags sql.NullString) []string {
	if !tags.Valid || tags.String == "" {
		return nil
	}
	var out []string
	if err := json.Unmarshal([]byte(tags.String), &out); err != nil {
		return nil
	}
	return out
}

func writeJSON(out *os.File, projects []project) error {
	if projects == nil {
		projects = []project{} // encode as [] rather than null
	}
	enc := json.NewEncoder(out)
	enc.SetIndent("", "  ")
	return enc.Encode(projects)
}

func writeTable(out *os.File, projects []project, view string) error {
	fmt.Fprintf(out, "project-registry (%s) — %d watched dir(s)\n\n", view, len(projects))
	if len(projects) == 0 {
		fmt.Fprintln(out, "  (empty — run the scanner: uv run main.py)")
		return nil
	}
	w := tabwriter.NewWriter(out, 0, 4, 2, ' ', 0)
	fmt.Fprintln(w, "PROJECT\tTYPE\tBRANCH\tCYCLE\tTAGS\tPATH")
	for _, p := range projects {
		fmt.Fprintf(w, "%s\t%s\t%s\t%s\t%s\t%s\n",
			orDash(p.Name), orDash(p.DirType), orDash(p.Branch),
			orDash(p.Cycle), orDash(strings.Join(p.Tags, ",")), p.Path)
	}
	return w.Flush()
}

func orDash(s string) string {
	if s == "" {
		return "-"
	}
	return s
}
