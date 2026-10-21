import {useEffect,useState} from 'react';
import {API} from '../services/api';
type Sheet={name:string;rows:string[][];row_count:number;column_count:number};
export function parseCsv(text:string):string[][] {
 const rows:string[][]=[];let row:string[]=[],cell='',quoted=false;
 for(let i=0;i<text.length;i++){const c=text[i];
  if(c==='"'){if(quoted&&text[i+1]==='"'){cell+='"';i++;}else quoted=!quoted;}
  else if(c===','&&!quoted){row.push(cell);cell='';}
  else if((c==='\n'||c==='\r')&&!quoted){if(c==='\r'&&text[i+1]==='\n')i++;row.push(cell);rows.push(row);row=[];cell='';}
  else cell+=c;
 }
 if(cell||row.length){row.push(cell);rows.push(row);}
 return rows.filter(r=>r.some(v=>v.trim())).map((r,i)=>i===0?r.map(v=>v.replace(/^\uFEFF/,'')):r);
}
export function SpreadsheetPreview({file,content,filename,search=''}:{file?:File;content?:string;filename:string;search?:string}){
 const [sheets,setSheets]=useState<Sheet[]>([]),[selected,setSelected]=useState(0),[error,setError]=useState(''),[loading,setLoading]=useState(true),[query,setQuery]=useState('');
 useEffect(()=>{let active=true;setLoading(true);setError('');setSheets([]);setSelected(0);setQuery('');
 (async()=>{if(/\.csv$/i.test(filename)){const rows=parseCsv(file?await file.text():content||'');return [{name:'CSV',rows,row_count:rows.length,column_count:rows.reduce((max,r)=>Math.max(max,r.length),0)}];}
 const blob=file || await (await fetch(content!)).blob();const form=new FormData();form.append('file',blob,filename);
 return (await API.send<{sheets:Sheet[]}>('/api/v1/preview',{method:'POST',body:form,form:true})).sheets;
 })().then(s=>{if(active)setSheets(s)}).catch(e=>{if(active)setError(e.message||'Preview unavailable.')}).finally(()=>{if(active)setLoading(false)});
 return()=>{active=false;};
 },[file,content,filename]);
 if(loading)return <p role="status">Loading spreadsheet preview…</p>;
 if(error)return <p role="alert">Could not preview this workbook: {error}</p>;
 const sheet=sheets[selected];if(!sheet)return <p>No non-empty worksheets found.</p>;
 const width=Math.min(sheet.column_count,60);const term=(search||query).toLowerCase();
 const rows=sheet.rows.slice(1).map((cells,i)=>({cells,index:i+2})).filter(r=>!term||r.cells.some(c=>c.toLowerCase().includes(term)));
 return <div className="spreadsheet-preview">
 <div className="sheet-toolbar"><label>Worksheet <select value={selected} onChange={e=>setSelected(Number(e.target.value))}>{sheets.map((s,i)=><option key={i} value={i}>{s.name}</option>)}</select></label><input aria-label="Search spreadsheet rows" placeholder="Search rows…" value={query} onChange={e=>setQuery(e.target.value)}/></div>
 <p className="sheet-note">{Math.max(0,sheet.row_count-1)} data rows · {sheet.column_count} columns · First row used as column headings. Preview limited to 200 rows and 60 columns.</p>
 <div className="sheet-scroll" tabIndex={0} aria-label="Spreadsheet table"><table><thead><tr><th>#</th>{Array.from({length:width},(_,i)=><th key={i}>{sheet.rows[0]?.[i]||'Column '+(i+1)}</th>)}</tr></thead><tbody>{rows.slice(0,200).map(r=><tr key={r.index}><th>{r.index}</th>{Array.from({length:width},(_,i)=><td key={i}>{r.cells[i]||''}</td>)}</tr>)}</tbody></table>{!rows.length&&<p>No matching rows.</p>}</div></div>;
}
