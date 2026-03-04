
                <tr>
                    <td style="padding:10px 26px 8px;">
                        <div style="padding:14px;border-radius:12px;background:rgba(18,13,33,0.7);border:1px solid rgba(198,154,255,0.16);">
                            <div style="font-size:11px;letter-spacing:.11em;text-transform:uppercase;color:#d6bcf7;margin-bottom:8px;">Čomu sa vyhnúť</div>
                            <ul style="margin:0;padding-left:16px;color:#ecdeff;font-size:14px;line-height:1.5;">
                                {% for item in ai.avoid %}
                                <li style="margin:0 0 6px;">{{ item }}</li>
                                {% empty %}
                                <li>Bez položiek.</li>
                                {% endfor %}
                            </ul>
                        </div>
                    </td>
                </tr>
                <tr>

                in the file @model_report_daily.html needs some refactoring I guess there are more "Bez položiek." let make code clean